import argparse
import io
import json
import math
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import threading
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import whatsapp
from .analysis import product_key
from .pipeline import Pipeline, now, settings_for
from .store import ROOT, Store

STATIC = Path(__file__).resolve().parent / "static"


def load_env(path):
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, equals, value = line.partition("=")
            key = key.strip()
            if equals and re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
                os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def state(pipeline, token):
    store = pipeline.store
    products = sorted(store.rows("products"), key=lambda item: -item.get("score", 0))
    videos = store.rows("videos")
    for product in products:
        folder = store.folder / "midia" / product_key(product["id"])
        product["has_media"] = any(folder.glob("produto.*"))
    counts = {
        "products": len(products), "selected": sum(bool(p.get("selected")) for p in products),
        "videos": len(videos), "published": sum(v["status"] == "published" for v in videos),
        "links": sum(bool(p.get("link")) for p in products),
        "estimated_commission": round(sum((p.get("price") or 0) * (p.get("commission_rate") or 0)
                                          for p in products if p.get("selected")), 2),
        "confirmed_commission": round(sum(v.get("confirmed_commission", 0) for v in videos), 2),
    }
    return dict(csrf=token, settings=pipeline.settings(), products=products, videos=videos, counts=counts,
                logs=store.logs(), paused=pipeline.paused(), running=pipeline.running,
                whatsapp_mode=whatsapp.enabled(), next_run=pipeline.next_run(), last_run=store.get("last_run"), configured=pipeline.configured())


def handler_for(pipeline, token, host):
    store = pipeline.store
    origin = f"http://{host}"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send_data(self, content, mime, status=200, filename=None):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cache-Control", "no-store")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(content)

        def json(self, payload, status=200):
            self.send_data(json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)

        def authorized(self, write=False):
            valid = self.headers.get("Host") == host and self.headers.get("Sec-Fetch-Site") not in ("cross-site", "same-site")
            if write:
                valid = valid and self.headers.get("Origin") == origin and secrets.compare_digest(
                    self.headers.get("X-Radar-Token", "").encode(), token.encode())
            if not valid:
                self.json({"error": "Acesso local inválido."}, 403)
            return valid

        def do_GET(self):
            if not self.authorized():
                return
            route = urlsplit(self.path)
            if route.path == "/api/state":
                self.json(state(pipeline, token))
                return
            if route.path in ("/api/video", "/api/package"):
                identifier = parse_qs(route.query).get("id", [""])[0]
                video = next((item for item in store.rows("videos") if item["id"] == identifier), None)
                if video is None:
                    self.json({"error": "Vídeo não encontrado."}, 404)
                    return
                path = store.folder / "videos" / video["filename"]
                if not path.is_file():
                    self.json({"error": "Arquivo de vídeo ausente."}, 404)
                    return
                if route.path == "/api/video":
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(path.stat().st_size))
                    self.end_headers()
                    with path.open("rb") as source:
                        try:
                            shutil.copyfileobj(source, self.wfile)
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                    return
                if video["status"] not in ("ready", "published"):
                    self.json({"error": "Aguarde a geração do link para baixar o pacote."}, 409)
                    return
                content = io.BytesIO()
                with zipfile.ZipFile(content, "w") as archive:
                    archive.write(path, "video.mp4")
                    archive.writestr("legenda.txt", video["caption"])
                    archive.writestr("produto.txt", f'Produto: {video["product_url"]}\nLink afiliado: {video["link"]}\n'
                                     "No app Shopee, anexe o produto pelo recurso de marcação antes de publicar.\n"
                                     "O link de afiliado é uma referência para uso fora da legenda do Shopee Vídeo.")
                self.send_data(content.getvalue(), "application/zip", filename=f"radar-{identifier}.zip")
                return
            name = route.path.lstrip("/") or "index.html"
            file = STATIC / name
            if file.resolve().parent != STATIC or not file.is_file():
                self.json({"error": "Página não encontrada."}, 404)
                return
            mime = mimetypes.guess_type(file)[0] or "application/octet-stream"
            self.send_data(file.read_bytes(), mime)

        def length(self, maximum):
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= maximum:
                raise ValueError("Arquivo ou solicitação acima do limite.")
            return length

        def media(self, route):
            query = parse_qs(route.query)
            product_id = query.get("id", [""])[0]
            suffix = Path(query.get("name", [""])[0]).suffix.lower()
            if suffix not in {".mp4", ".mov", ".m4v", ".webm"}:
                raise ValueError("Envie um clipe MP4, MOV, M4V ou WEBM autorizado.")
            if not any(p["id"] == product_id for p in store.rows("products")):
                raise ValueError("Produto não encontrado.")
            length = self.length(150 * 1024 * 1024)
            if not length:
                raise ValueError("Arquivo vazio.")
            folder = store.folder / "midia" / product_key(product_id)
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / ("produto" + suffix)
            temporary = folder / secrets.token_hex(12)
            try:
                with temporary.open("wb") as output:
                    remaining = length
                    while remaining:
                        block = self.rfile.read(min(remaining, 1024 * 1024))
                        if not block:
                            raise ValueError("Envio incompleto.")
                        output.write(block)
                        remaining -= len(block)
                with pipeline.lock:
                    if pipeline.running:
                        raise ValueError("Aguarde a execução terminar antes de trocar o clipe.")
                    temporary.replace(target)
                    for old in folder.glob("produto.*"):
                        if old != target:
                            old.unlink()
            finally:
                temporary.unlink(missing_ok=True)

        def record(self, operation, body):
            with pipeline.lock:
                if pipeline.running:
                    raise ValueError("Aguarde a execução terminar.")
                video = next((v for v in store.rows("videos") if v["id"] == body.get("id")), None)
                if video is None:
                    raise ValueError("Vídeo não encontrado.")
                if operation == "/api/published":
                    publication = body.get("publication_id")
                    if video["status"] not in ("ready", "published") or not isinstance(publication, str) or not publication.strip() or len(publication) > 250:
                        raise ValueError("Informe o identificador da publicação para um vídeo com pacote pronto.")
                    video.update(status="published", publication_id=publication.strip(), published_at=now().isoformat())
                    store.log("publication", "ok", f'Publicação registrada manualmente para {video["id"]}.')
                else:
                    amount = body.get("confirmed_commission")
                    if video["status"] != "published" or type(amount) not in (int, float) or not 0 <= amount <= 100000000 or not math.isfinite(amount):
                        raise ValueError("Informe um valor válido para um vídeo publicado.")
                    video.update(confirmed_commission=round(amount, 2), results_at=now().isoformat())
                store.save("videos", [video])

        def do_POST(self):
            if not self.authorized(write=True):
                return
            route = urlsplit(self.path)
            try:
                if route.path == "/api/media":
                    self.media(route)
                else:
                    raw = self.rfile.read(self.length(32000))
                    body = json.loads(raw) if raw else {}
                    if not isinstance(body, dict):
                        raise ValueError("Solicitação inválida.")
                    if route.path == "/api/settings":
                        store.set("settings", settings_for(body))
                    elif route.path == "/api/run":
                        if not pipeline.configured():
                            raise ValueError("Configure as credenciais Shopee no arquivo .env.")
                        if not pipeline.start():
                            raise ValueError("A execução está ativa ou pausada.")
                    elif route.path in ("/api/pause", "/api/resume"):
                        pipeline.pause(route.path == "/api/pause")
                    elif route.path == "/api/backup":
                        file = store.backup()
                        self.json({"ok": True, "path": str(file)})
                        return
                    elif route.path in ("/api/published", "/api/results"):
                        self.record(route.path, body)
                    else:
                        self.json({"error": "Operação desconhecida."}, 404)
                        return
            except (ValueError, OSError) as error:
                self.json({"error": str(error) if isinstance(error, ValueError) else "Falha ao acessar os dados locais."}, 400)
                return
            self.json({"ok": True})

    return Handler


def open_browser(url):
    for key in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        base = os.getenv(key)
        if base:
            chrome = Path(base) / "Google/Chrome/Application/chrome.exe"
            if chrome.is_file():
                subprocess.Popen([str(chrome), url], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                return
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    load_env(ROOT / ".env")
    pipeline = Pipeline(Store())
    host = f"127.0.0.1:{args.port}"
    handler = handler_for(pipeline, secrets.token_urlsafe(32), host)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError:
        parser.exit(1, "Porta ocupada. Se o Radar estiver aberto, acesse http://127.0.0.1:8765.\n")
    shutdown = threading.Event()
    threading.Thread(target=pipeline.schedule, args=(shutdown,), daemon=True).start()
    print(f"RADAR SHOPEE AI | http://{host}", flush=True)
    if not args.no_browser:
        threading.Thread(target=open_browser, args=(f"http://{host}",), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown.set()
        pipeline.stop.set()
        server.server_close()
        if pipeline.worker:
            pipeline.worker.join(timeout=5)


if __name__ == "__main__":
    main()

