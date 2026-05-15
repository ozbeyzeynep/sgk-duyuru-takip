import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime

# ── Ayarlar ──────────────────────────────────────────────────────────────────
SGK_URL = "https://www.sgk.gov.tr/duyuru"
ANAHTAR_KELIME = "bedeli ödenecek"          # büyük/küçük harf duyarsız arama
DURUM_DOSYASI = "gorulmus_duyurular.json"   # daha önce görülen duyurular
TEAMS_WEBHOOK = os.environ["TEAMS_WEBHOOK_URL"]  # GitHub Secret'tan gelir
# ─────────────────────────────────────────────────────────────────────────────


def gorulmusleri_yukle():
    if os.path.exists(DURUM_DOSYASI):
        with open(DURUM_DOSYASI, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def gorulmusleri_kaydet(liste):
    with open(DURUM_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, indent=2)


def duyurulari_cek():
    """SGK duyurular sayfasını çekip 'bedeli ödenecek' geçen duyuruları döndür."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SGKChecker/1.0)"}
    r = requests.get(SGK_URL, headers=headers, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    duyurular = []
    # SGK duyuru listesindeki her bağlantıyı tara
    for a in soup.find_all("a", href=True):
        metin = a.get_text(strip=True)
        if ANAHTAR_KELIME.lower() in metin.lower():
            href = a["href"]
            if not href.startswith("http"):
                href = "https://www.sgk.gov.tr" + href
            duyurular.append({"baslik": metin, "url": href})

    return duyurular


def excel_linki_bul(duyuru_url):
    """Duyuru sayfasına gir, içindeki Excel linkini bul."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SGKChecker/1.0)"}
    r = requests.get(duyuru_url, headers=headers, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"\.(xlsx|xls|xlsm)", href, re.IGNORECASE) or "DownloadFile" in href:
            if not href.startswith("http"):
                href = "https://www.sgk.gov.tr" + href
            return href

    return None


def teams_bildirimi_gonder(baslik, duyuru_url, excel_url):
    """Teams kanalına Adaptive Card formatında bildirim gönder."""
    tarih = datetime.now().strftime("%d.%m.%Y %H:%M")

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "🔔 SGK'da Yeni Duyuru!",
                            "weight": "Bolder",
                            "size": "Large",
                            "color": "Accent"
                        },
                        {
                            "type": "TextBlock",
                            "text": baslik,
                            "wrap": True,
                            "spacing": "Small"
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "📅 Tespit tarihi", "value": tarih},
                                {"title": "📎 Excel", "value": "Mevcut ✅" if excel_url else "Bulunamadı ⚠️"}
                            ]
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "Duyuruyu Aç",
                            "url": duyuru_url
                        }
                    ] + ([
                        {
                            "type": "Action.OpenUrl",
                            "title": "Excel'i İndir",
                            "url": excel_url
                        }
                    ] if excel_url else [])
                }
            }
        ]
    }

    r = requests.post(TEAMS_WEBHOOK, json=payload, timeout=15)
    r.raise_for_status()
    print(f"✅ Teams bildirimi gönderildi: {baslik}")


def main():
    print(f"[{datetime.now().strftime('%d.%m.%Y %H:%M')}] SGK duyuruları kontrol ediliyor...")

    gorulmusler = gorulmusleri_yukle()
    gorulmus_urllar = {d["url"] for d in gorulmusler}

    yeni_duyurular = duyurulari_cek()
    print(f"'{ANAHTAR_KELIME}' içeren {len(yeni_duyurular)} duyuru bulundu.")

    yeni_eklenenler = [d for d in yeni_duyurular if d["url"] not in gorulmus_urllar]
    print(f"Daha önce görülmemiş: {len(yeni_eklenenler)} duyuru.")

    for duyuru in yeni_eklenenler:
        print(f"  → İşleniyor: {duyuru['baslik'][:60]}...")
        excel_url = excel_linki_bul(duyuru["url"])
        teams_bildirimi_gonder(duyuru["baslik"], duyuru["url"], excel_url)
        gorulmusler.append(duyuru)

    gorulmusleri_kaydet(gorulmusler)
    print("Tamamlandı.")


if __name__ == "__main__":
    main()
