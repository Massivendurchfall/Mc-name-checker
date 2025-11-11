#!/usr/bin/env python3
import threading
import time
import string
import random
import os
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor
import requests

def quelle_auswahl():
    print("API wählen:")
    print("[1] Mojang Offiziell (streng limitiert)")
    print("[2] Ashcon Inoffiziell (schneller, Cache) [Standard]")
    a = input("Eingabe 1/2: ").strip()
    if a == "1":
        return "official"
    if a == "2" or a == "":
        return "ashcon"
    print("Ungültig, Standard: Ashcon")
    return "ashcon"

def zeichen_auswahl():
    print("\nZeichenmodus wählen:")
    print("[1] Nur Buchstaben (a-z)")
    print("[2] Buchstaben + Zahlen (a-z0-9)")
    a = input("Eingabe 1/2: ").strip()
    if a == "1":
        return string.ascii_lowercase
    if a == "2":
        return string.ascii_lowercase + string.digits
    print("Ungültig, Standard: Buchstaben + Zahlen")
    return string.ascii_lowercase + string.digits

def check_official(sess, name, timeout):
    url = f"https://api.mojang.com/users/profiles/minecraft/{name}"
    try:
        r = sess.get(url, timeout=timeout)
    except requests.RequestException:
        return None
    if r.status_code == 200:
        return "belegt"
    if r.status_code in (204, 404):
        return "nicht_belegt_unbestaetigt"
    if r.status_code == 429:
        return "rate"
    return None

def check_ashcon(sess, name, timeout):
    url = f"https://api.ashcon.app/mojang/v2/user/{name}"
    try:
        r = sess.get(url, timeout=timeout)
    except requests.RequestException:
        return None
    if r.status_code == 200:
        return "belegt"
    if r.status_code == 404:
        return "nicht_belegt_unbestaetigt"
    if r.status_code == 429:
        return "rate"
    return None

def checker(quelle):
    if quelle == "official":
        return check_official
    return check_ashcon

def generator(charset, length):
    rng = random.Random()
    while True:
        yield "".join(rng.choice(charset) for _ in range(length))

def producer(q, stop_event, charset, length):
    gen = generator(charset, length)
    while not stop_event.is_set():
        q.put(next(gen))

def consumer(q, sess, fn, timeout, rate_sleep, datei_lock, datei, gesehen, stats, stop_event):
    while not stop_event.is_set():
        try:
            name = q.get(timeout=0.1)
        except Empty:
            continue
        if name in gesehen:
            q.task_done()
            continue
        gesehen.add(name)
        while not stop_event.is_set():
            res = fn(sess, name, timeout)
            if res == "belegt":
                stats["geprueft"] += 1
                print(f"Belegt: {name}")
                break
            if res == "nicht_belegt_unbestaetigt":
                stats["geprueft"] += 1
                stats["unbestaetigt"] += 1
                print(f"Nicht belegt (unbestätigt): {name}")
                with datei_lock:
                    with open(datei, "a", encoding="utf-8") as f:
                        f.write(name + "\n")
                break
            if res == "rate":
                print(f"Rate Limit erreicht – warte {rate_sleep}s und prüfe erneut: {name}")
                time.sleep(rate_sleep)
                continue
            print(f"Fehler bei: {name} – warte 5s und versuche erneut")
            time.sleep(5)
        q.task_done()

def main():
    quelle = quelle_auswahl()
    charset = zeichen_auswahl()
    laenge = 4
    threads = 8 if quelle == "official" else 12
    timeout = 6.0
    rate_sleep = 60.0 if quelle == "official" else 20.0
    datei = "verfuegbare_namen.txt"
    if os.path.exists(datei):
        os.remove(datei)

    sess = requests.Session()
    sess.headers.update({"User-Agent": "mc-name-checker/zweiquellen-ohne-emojis"})
    q = Queue(maxsize=threads * 3)
    stop_event = threading.Event()
    gesehen = set()
    stats = {"geprueft": 0, "unbestaetigt": 0}
    datei_lock = threading.Lock()

    print(f"\nStarte Prüfung ({'Mojang' if quelle=='official' else 'Ashcon'}) – Hinweis: 'Nicht belegt' ist ohne Login nicht sicher claimbar.")
    print(f"Zeichensatz: {'a-z' if charset == string.ascii_lowercase else 'a-z0-9'} – Länge: {laenge}")
    print("Beenden mit STRG+C.\n")

    prod = threading.Thread(target=producer, args=(q, stop_event, charset, laenge), daemon=True)
    prod.start()

    pool = ThreadPoolExecutor(max_workers=threads)
    fn = checker(quelle)
    for _ in range(threads):
        pool.submit(consumer, q, sess, fn, timeout, rate_sleep, datei_lock, datei, gesehen, stats, stop_event)

    start = time.time()
    try:
        while True:
            time.sleep(2)
            dur = int(time.time() - start)
            print(f"Status: geprüft={stats['geprueft']} | nicht_belegt_unbestaetigt={stats['unbestaetigt']} | laufzeit={dur}s")
    except KeyboardInterrupt:
        print("\nBeendet.")
        stop_event.set()
        prod.join()
        q.join()
        pool.shutdown(wait=False, cancel_futures=True)
        dur = int(time.time() - start)
        print(f"\nGesamt geprüft: {stats['geprueft']}")
        print(f"Nicht belegt (unbestätigt): {stats['unbestaetigt']}")
        print(f"Dauer: {dur}s")
        print(f"Gespeichert in: {datei}\n")

if __name__ == "__main__":
    main()
