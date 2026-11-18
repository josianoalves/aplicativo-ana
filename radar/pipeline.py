import os
import re
import threading
from datetime import datetime, timedelta, timezone

from . import azure_voice, whatsapp
from .analysis import analyze, product_key, script_for
from .store import DEFAULT
from .video import MUSIC_EXTENSIONS

TZ = timezone(timedelta(hours=-3), "Fortaleza")


def now():
    return datetime.now(TZ)


def settings_for(value):
    if not isinstance(value, dict) or not isinstance(value.get("times"), dict):
        raise ValueError("Configuração inválida.")
    result = {"times": {}}
    keywords = value.get("keywords")
    if not isinstance(keywords, str) or len(keywords) > 400 or any(len(word.strip()) > 200 for word in keywords.split(",")):
        raise ValueError("Use até 400 caracteres no total e 200 por termo.")
    result["keywords"] = keywords.strip()
    for name, minimum, maximum in [("limit", 1, 100), ("select", 1, 10), ("variants", 2, 3), ("duration", 15, 45)]:
        number = value.get(name)
        if type(number) is not int or not minimum <= number <= maximum:
            raise ValueError(f"Campo {name}: use um valor de {minimum} a {maximum}.")
        result[name] = number
    if result["select"] > result["limit"]:
        raise ValueError("A seleção não pode exceder o limite da pesquisa.")
    for stage in DEFAULT["times"]:
        time = value["times"].get(stage)
        if not isinstance(time, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time, re.ASCII):
            raise ValueError("Use horários no formato HH:MM.")
        result["times"][stage] = time
    times = list(result["times"].values())
    if times != sorted(times):
        raise ValueError("Os horários devem seguir a ordem das etapas.")
    return result


class Cancelled(Exception):
    pass


class Pipeline:
    def __init__(self, store, client_factory=None, renderer=None):
        self.store = store
        self.client_factory = client_factory or self.client
        self.renderer = renderer
        self.stop = threading.Event()
        self.worker = None
        self.lock = threading.RLock()
        self.running = False

    @staticmethod
    def configured():
        return bool(os.getenv("SHOPEE_APP_ID") and os.getenv("SHOPEE_SECRET"))

    @staticmethod
    def client():
        if not Pipeline.configured():
            raise ValueError("Configure SHOPEE_APP_ID e SHOPEE_SECRET no arquivo .env e reinicie.")
        from .shopee import Shopee
        return Shopee(os.environ["SHOPEE_APP_ID"], os.environ["SHOPEE_SECRET"])

    def settings(self):
        return self.store.get("settings", DEFAULT)

    def paused(self):
        return self.store.get("paused", False)

    def pause(self, value):
        with self.lock:
            self.store.set("paused", value)
            if value:
                self.stop.set()

    def start(self, scheduled=None):
        with self.lock:
            if self.running or self.paused():
                return False
            self.stop.clear()
            self.running = True
            if scheduled:
                self.store.set("schedule_day", scheduled.date().isoformat())
            self.worker = threading.Thread(target=self.execute, args=(scheduled,), daemon=True)
            self.worker.start()
            return True

    def next_run(self):
        if self.paused():
            return None
        current = now()
        hour, minute = map(int, self.settings()["times"]["research"].split(":"))
        target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= current or self.store.get("schedule_day") == current.date().isoformat():
            target += timedelta(days=1)
        return target.isoformat()

    def schedule(self, shutdown):
        while not shutdown.is_set():
            current = now()
            hour, minute = map(int, self.settings()["times"]["research"].split(":"))
            target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
            within_window = target <= current and (whatsapp.enabled() or current < target + timedelta(minutes=30))
            if (within_window and
                    self.store.get("schedule_day") != current.date().isoformat()):
                self.start(target)
            shutdown.wait(10)

    def check_stop(self):
        if self.stop.is_set():
            raise Cancelled()

    def retry(self, stage, action):
        for attempt in range(1, 3):
            self.check_stop()
            try:
                return action()
            except Cancelled:
                raise
            except Exception:
                self.check_stop()
                if attempt == 2:
                    raise
                self.store.log(stage, "retry", "Falha na primeira tentativa. Repetindo em 2 segundos.")
                self.stop.wait(2)

    def daily_whatsapp(self, client, stamp, report):
        whatsapp.configuration()
        day = stamp[:10]
        record = self.store.get("whatsapp_dispatch", {})
        if record.get("day") == day:
            report["whatsapp"] = record["status"]
            self.store.log("whatsapp", "ok", "Já houve uma tentativa de envio hoje. Consulte o histórico e o WhatsApp.")
            return
        catalog = self.retry("research", lambda: client.products("", max(30, self.settings()["limit"])))
        ranked = sorted((p for p in catalog if type(p.get("sales")) is int and p["sales"] > 0),
                        key=lambda p: (-p["sales"], str(p["id"])))[:3]
        report["found"] = len(catalog)
        report["selected"] = len(ranked)
        report["discarded"] = len(catalog) - len(ranked)
        if len(ranked) != 3:
            raise ValueError("A Shopee retornou menos de três produtos com vendas informadas. Envio cancelado.")
        existing = {p["id"]: p for p in self.store.rows("products")}
        for product in ranked:
            current = existing.get(str(product["id"]), {})
            if current.get("url") == product["url"] and current.get("link"):
                product["link"] = current["link"]
            else:
                product["link"] = self.retry("links", lambda: client.link(product["url"]))
                report["links"] += 1
        self.check_stop()
        for product in catalog:
            product["id"] = str(product["id"])
            old = existing.get(product["id"], {})
            if old.get("url") == product["url"] and old.get("link"):
                product.setdefault("link", old["link"])
            product.update(analyze(product), researched_at=stamp,
                           selected=product in ranked, decision="Ranking por vendas informadas pela Shopee.")
        for identifier, product in existing.items():
            if product.get("selected") and not any(item["id"] == identifier for item in catalog):
                product["selected"] = False
                self.store.save("products", [product])
        self.store.save("products", catalog, stamp)
        self.check_stop()
        # Reserve before sending because a network timeout can occur after Meta accepts the request.
        self.store.set("whatsapp_dispatch", {"day": day, "status": "attempted"})
        message_id = whatsapp.send([p["link"] for p in ranked])
        self.store.set("whatsapp_dispatch", {"day": day, "status": "accepted", "message_id": message_id})
        report["whatsapp"] = "accepted"
        self.store.log("whatsapp", "ok", "A Meta aceitou a mensagem com os três links.")

    def execute(self, scheduled=None):
        settings = self.settings()
        stamp = now().isoformat()
        stage = "research"
        report = {"found": 0, "selected": 0, "discarded": 0, "videos": 0, "links": 0, "publications": 0,
                  "started": stamp}
        status = "ok"

        def enter(name):
            nonlocal stage
            stage = name
            if scheduled and name in settings["times"]:
                hour, minute = map(int, settings["times"][name].split(":"))
                target = scheduled.replace(hour=hour, minute=minute)
                self.stop.wait(max(0, (target - now()).total_seconds()))
            self.check_stop()
            self.store.log(name, "running", "Etapa iniciada.")

        try:
            enter("research")
            client = self.client_factory()
            if whatsapp.enabled():
                stage = "whatsapp"
                self.daily_whatsapp(client, stamp, report)
                return
            previous = {str(p["id"]): p for p in self.store.rows("products")}
            products = {}
            keywords = list(dict.fromkeys(word.strip() for word in settings["keywords"].split(",") if word.strip())) or [""]
            per_keyword = max(1, (settings["limit"] + len(keywords) - 1) // len(keywords))
            for keyword in keywords:
                for product in self.retry(stage, lambda: client.products(keyword, per_keyword)):
                    key = str(product["id"])
                    old = previous.get(key, {})
                    product.update(id=key, researched_at=stamp, selected=False)
                    product["link"] = old.get("link") if old.get("url") == product["url"] else None
                    before, after = old.get("sales"), product.get("sales")
                    product["trend"] = (after - before) / before if before and after is not None else None
                    products[key] = product
            found = list(products.values())[:settings["limit"]]
            report["found"] = len(found)
            self.check_stop()
            self.store.save("products", found, stamp)
            enter("analyze")
            for product in found:
                product.update(analyze(product))
            self.store.save("products", found)
            enter("select")
            ordered = sorted(found, key=lambda p: (-p["score"], p["id"]))
            selected = [p for p in ordered if p["grade"] in ("A", "B")][:settings["select"]]
            report["selected"] = len(selected)
            report["discarded"] = len(found) - len(selected)
            for product in previous.values():
                if product["id"] not in products and product.get("selected"):
                    product["selected"] = False
                    self.store.save("products", [product])
            for product in selected:
                product["selected"] = True
            for product in found:
                product["decision"] = ("Selecionado pela pontuação." if product["selected"] else
                                       "Nota abaixo de 40." if product["grade"] == "C" else "Fora do limite diário.")
            self.store.save("products", found)
            enter("script")
            existing = {v["id"]: v for v in self.store.rows("videos")}
            jobs = []
            azure_enabled = azure_voice.enabled()
            voices = azure_voice.VOICES if azure_enabled else (None,) * settings["variants"]
            for product in selected:
                for variant, voice in enumerate(voices, 1):
                    identifier = f'{product_key(product["id"])}-{variant}'
                    if voice:
                        identifier += "-azure"
                    old_video = existing.get(identifier)
                    if old_video and (old_video["status"] == "published" or
                                      (self.store.folder / "videos" / old_video["filename"]).is_file()):
                        continue
                    script = self.retry(stage, lambda: script_for(product, variant))
                    jobs.append((product, variant, identifier, script, voice))
            enter("video")
            target = self.store.folder / "videos"
            target.mkdir(exist_ok=True)
            if jobs and self.renderer is None:
                from .video import render
                self.renderer = render
            music = next((file for file in sorted((self.store.folder / "musica").glob("*"))
                          if file.is_file() and file.suffix.lower() in MUSIC_EXTENSIONS), None)
            for product, variant, identifier, script, voice in jobs:
                self.check_stop()
                folder = self.store.folder / "midia" / product_key(product["id"])
                media = next(iter(sorted(folder.glob("produto.*"))), None)
                if media is None:
                    self.store.log(stage, "pending", f'{product["name"]}: envie um clipe autorizado no painel.')
                    continue
                output = target / (identifier + ".mp4")
                self.retry(stage, lambda: self.renderer(product, script, media, output, settings["duration"],
                                                       variant, music, self.stop))
                self.check_stop()
                video = {"id": identifier, "filename": output.name, "product_id": product["id"],
                         "variant": variant, "voice": voice, "script": script, "caption": script["caption"], "status": "rendered",
                         "at": now().isoformat()}
                self.store.save("videos", [video])
                report["videos"] += 1
            enter("links")
            for product in selected:
                if not product.get("link"):
                    product["link"] = self.retry(stage, lambda: client.link(product["url"]))
                    self.check_stop()
                    self.store.save("products", [product])
                    report["links"] += 1
                for video in self.store.rows("videos"):
                    if video["product_id"] == product["id"] and video["status"] == "rendered":
                        video.update(status="ready", link=product["link"], product_url=product["url"])
                        self.store.save("videos", [video])
        except Cancelled:
            status = "cancelled"
            self.store.log(stage, status, "Execução interrompida.")
        except Exception as error:
            status = "error"
            report["failure"] = stage
            message = str(error) if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__
            for secret in (os.getenv("SHOPEE_SECRET"), os.getenv("OPENAI_API_KEY"), os.getenv("SHOPEE_APP_ID"),
                           os.getenv("WHATSAPP_TOKEN"), os.getenv("WHATSAPP_DESTINO")):
                if secret:
                    message = message.replace(secret, "[oculto]")
            self.store.log(stage, status, message[:400])
        finally:
            report.update(status=status, finished=now().isoformat())
            self.store.set("last_run", report)
            self.store.log("report", status, f'{report["found"]} encontrados, {report["selected"]} selecionados, '
                           f'{report["discarded"]} descartados, {report["videos"]} vídeos, {report["links"]} links.')
            with self.lock:
                self.running = False




