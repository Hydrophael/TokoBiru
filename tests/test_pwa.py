"""Tes PWA: manifest, ikon, service worker, dan tautan di halaman utama."""
import json


def test_halaman_utama_menautkan_manifest_dan_pwa_js(anon):
    html = anon.get("/").get_data(as_text=True)
    assert 'rel="manifest" href="/static/manifest.json"' in html
    assert "/static/pwa.js" in html


def test_manifest_valid_dan_semua_ikon_ada(anon):
    resp = anon.get("/static/manifest.json")
    assert resp.status_code == 200
    manifest = json.loads(resp.get_data(as_text=True))
    assert manifest["display"] == "standalone" and manifest["start_url"] == "/"
    assert manifest["name"] and manifest["short_name"]

    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(icon["purpose"] == "maskable" for icon in manifest["icons"])
    for icon in manifest["icons"]:
        res = anon.get(icon["src"])
        assert res.status_code == 200 and res.mimetype == "image/png"


def test_ikon_apple_ada(anon):
    assert anon.get("/static/icons/apple-touch-icon.png").status_code == 200


def test_service_worker_disajikan_dari_akar(anon):
    resp = anon.get("/sw.js")
    assert resp.status_code == 200
    assert "javascript" in resp.mimetype
    assert "no-cache" in resp.headers["Cache-Control"]
    assert b"/api/" in resp.get_data()          # aturan: data API tidak disimpan


def test_pwa_js_dimuat(anon):
    assert anon.get("/static/pwa.js").status_code == 200