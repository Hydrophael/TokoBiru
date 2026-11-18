"""Uji endpoint /proof/check dengan Flask test client + MongoDB tiruan. Jalankan dari folder proyek: pip install mongomock lalu python scripts/check_proof_endpoint.py (pemanggilan AI di-mock, tidak memakai kunci asli)."""
import os, sys, json
from datetime import datetime, timedelta
from unittest import mock
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else ".")
os.environ.update(SECRET_KEY="uji", GEMINI_API_KEY="kunci-uji", PROOF_BANK_HINT="4821")
import mongomock
from bson import ObjectId
from werkzeug.security import generate_password_hash
import app as tb

db = mongomock.MongoClient().tokobiru
tb._db = db
tb.PROOF_CONFIRM_READ = False   # bagian 1-16 menguji alur satu kali baca; bacaan kedua diuji di bagian 17-23
now = tb.utcnow()
def mkuser(name, role):
    return db.users.insert_one({"username": name, "email": name + "@x.id", "name": name.title(), "role": role,
        "password_hash": generate_password_hash("rahasia123"), "active": True, "failed": 0}).inserted_id
admin, other_admin, cust = mkuser("admin1", "admin"), mkuser("admin2", "admin"), mkuser("budi", "user")

def mkorder(code, total=87500, proof=b"\xff\xd8\xff-foto-A", method="transfer"):
    oid = ObjectId()
    created = now - timedelta(minutes=30)
    db.orders.insert_one({"_id": oid, "code": code, "user_id": cust, "username": "budi", "items": [], "subtotal": total - 10000,
        "shipping_fee": 10000, "total": total, "payment_method": method, "status": "pending",
        "created_at": created, "updated_at": created, "proof_at": now - timedelta(minutes=10)})
    if proof:
        db.order_proofs.insert_one({"_id": oid, "image": proof, "type": "image/jpeg", "uploaded_at": now})
    return str(oid)

def client(username):
    c = tb.app.test_client()
    csrf = c.get("/api/auth/me").get_json()["csrf"]
    r = c.post("/api/auth/login", json={"identifier": username, "password": "rahasia123"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.get_json()
    c.csrf = r.get_json()["csrf"]
    return c
def post(c, path, body=None):
    return c.post(path, json=body or {}, headers={"X-CSRF-Token": c.csrf})

# WIB 14:32 = 07:32 UTC ... pesanan dibuat now-30m; pakai waktu relatif supaya lolos aturan waktu
wib = lambda dt: (dt + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M")
good = {"is_proof": True, "amount": 87500, "time": datetime.strptime(wib(now - timedelta(minutes=12)), "%Y-%m-%d %H:%M"),
        "destination": "BCA 4821", "reference": "REF778899", "confidence": 0.95}

ok = 0
def check(name, cond):
    global ok
    assert cond, "GAGAL: " + name
    ok += 1; print("ok -", name)

a, a2, u = client("admin1"), client("admin2"), client("budi")
o1 = mkorder("TB-1")

# 1. pelanggan tidak boleh memakai endpoint staf
check("pelanggan ditolak (403)", post(u, f"/api/orders/{o1}/proof/check").status_code == 403)

# 2. cocok, dan hasil tersimpan
with mock.patch.object(tb, "read_transfer_proof", return_value=good) as m:
    r = post(a, f"/api/orders/{o1}/proof/check")
    check("staf berhasil (200)", r.status_code == 200)
    pc = r.get_json()["order"]["proof_check"]
    check("verdict match", pc["verdict"] == "match")
    check("model dipanggil sekali", m.call_count == 1)
    # 3. panggilan kedua memakai cache: AI tidak dipanggil lagi
    r2 = post(a2, f"/api/orders/{o1}/proof/check")
    check("cache: panggilan kedua tidak memanggil AI", m.call_count == 1 and r2.get_json()["order"]["proof_check"]["verdict"] == "match")
check("hasil tersimpan di dokumen pesanan", db.orders.find_one({"_id": ObjectId(o1)})["proof_check"]["reference"] == "REF778899")
check("sha256 tersimpan di bukti", len(db.order_proofs.find_one({"_id": ObjectId(o1)}).get("sha256", "")) == 64)
check("tercatat di log audit", db.logs.count_documents({"action": "bukti_dibaca"}) == 1)

# 4. pelanggan tidak melihat proof_check di daftar pesanannya
cust_orders = u.get("/api/orders").get_json()
orders = cust_orders.get("orders", cust_orders if isinstance(cust_orders, list) else [])
check("proof_check tersembunyi dari pelanggan", orders and all("proof_check" not in x for x in orders))
staff_orders = a.get("/api/orders").get_json()
staff_list = staff_orders.get("orders", staff_orders if isinstance(staff_orders, list) else [])
check("proof_check terlihat oleh staf", any("proof_check" in x for x in staff_list))

# 5. foto yang sama dipakai di pesanan lain -> mencurigakan; referensi sama juga
o2 = mkorder("TB-2", proof=b"\xff\xd8\xff-foto-A")
with mock.patch.object(tb, "read_transfer_proof", return_value=dict(good, reference="REF000111")):
    pc = post(a, f"/api/orders/{o2}/proof/check").get_json()["order"]["proof_check"]
check("foto sama dengan pesanan lain -> suspicious", pc["verdict"] == "suspicious")
o3 = mkorder("TB-3", proof=b"\xff\xd8\xff-foto-B")
with mock.patch.object(tb, "read_transfer_proof", return_value=dict(good, reference="REF778899")):
    pc = post(a, f"/api/orders/{o3}/proof/check").get_json()["order"]["proof_check"]
check("referensi sama dengan pesanan lain -> suspicious", pc["verdict"] == "suspicious")

# 6. nominal beda
o4 = mkorder("TB-4", proof=b"\xff\xd8\xff-foto-C")
with mock.patch.object(tb, "read_transfer_proof", return_value=dict(good, amount=78500, reference="REF424242")):
    pc = post(a, f"/api/orders/{o4}/proof/check").get_json()["order"]["proof_check"]
check("nominal beda -> mismatch", pc["verdict"] == "mismatch")

# 7. AI gagal -> 502 dan tidak ada hasil tersimpan
o5 = mkorder("TB-5", proof=b"\xff\xd8\xff-foto-D")
with mock.patch.object(tb, "read_transfer_proof", side_effect=tb.ProofReadError("HTTP 429")):
    r = post(a, f"/api/orders/{o5}/proof/check")
check("AI gagal -> 502", r.status_code == 502 and "proof_check" not in db.orders.find_one({"_id": ObjectId(o5)}))

# 8. tanpa bukti / bukan transfer / id ngawur
o6 = mkorder("TB-6", proof=None)
check("tanpa bukti -> 404", post(a, f"/api/orders/{o6}/proof/check").status_code == 404)
o7 = mkorder("TB-7", method="cash")
check("bukan transfer -> 404", post(a, f"/api/orders/{o7}/proof/check").status_code == 404)
check("id tidak valid -> 400", post(a, "/api/orders/xyz/proof/check").status_code == 400)
check("tanpa CSRF -> 403", a.post(f"/api/orders/{o1}/proof/check", json={}).status_code == 403)

# 9. fitur nonaktif tanpa kunci
with mock.patch.object(tb, "PROOF_READER_ENABLED", False):
    o8 = mkorder("TB-8", proof=b"\xff\xd8\xff-foto-E")
    check("tanpa kunci API -> 503", post(a, f"/api/orders/{o8}/proof/check").status_code == 503)

# 10. /auth/me memuat penanda
check("/auth/me membawa proof_reader", tb.app.test_client().get("/api/auth/me").get_json().get("proof_reader") is True)

# 11. unggah ulang bukti oleh pelanggan menghapus hasil lama dan menyimpan sha256
import base64
tiny_png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()
with mock.patch.object(tb, "read_transfer_proof", return_value=dict(good, reference="REF555666")):
    r = post(u, f"/api/orders/{o1}/proof", {"image": "data:image/png;base64," + tiny_png})
check("unggah ulang berhasil", r.status_code == 200)
doc = db.orders.find_one({"_id": ObjectId(o1)})
check("unggah memicu baca otomatis (proof_check baru)", doc.get("proof_check", {}).get("reference") == "REF555666")
check("unggah ulang menyimpan sha256 baru", len(db.order_proofs.find_one({"_id": ObjectId(o1)}).get("sha256", "")) == 64)
check("respons unggah tidak membocorkan proof_check", "proof_check" not in r.get_json()["order"])

# 12. pembacaan saat unggah gagal -> unggahan tetap berhasil, tanpa proof_check
o9 = mkorder("TB-9", proof=None)
db.orders.update_one({"_id": ObjectId(o9)}, {"$unset": {"proof_at": ""}})
with mock.patch.object(tb, "read_transfer_proof", side_effect=tb.ProofReadError("timeout")):
    r = post(u, f"/api/orders/{o9}/proof", {"image": "data:image/png;base64," + tiny_png})
check("AI gagal saat unggah -> unggahan tetap 200", r.status_code == 200 and "proof_check" not in db.orders.find_one({"_id": ObjectId(o9)}))
# 13. notifikasi staf memuat verdict
o10 = mkorder("TB-10", proof=None)
with mock.patch.object(tb, "read_transfer_proof", return_value=dict(good, reference="REF909090")), \
     mock.patch.object(tb, "push_staff") as push:
    other_png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"1" * 64).decode()  # foto berbeda agar tidak dianggap duplikat
    post(u, f"/api/orders/{o10}/proof", {"image": "data:image/png;base64," + other_png})
check("notifikasi staf memuat verdict", push.called and "Cocok" in push.call_args[0][1] and "TB-10" in push.call_args[0][1])

# 14. batas baca otomatis per pelanggan per jam: unggahan tetap berhasil, tetapi AI tidak dipanggil lagi
with mock.patch.object(tb, "read_transfer_proof", return_value=dict(good, reference="REF121212")) as m:
    for i in range(tb.PROOF_AUTO_READS_PER_HOUR):          # sisa kuota dihabiskan (unggahan sebelumnya ikut terhitung)
        oid = mkorder(f"TB-Q{i}", proof=None)
        post(u, f"/api/orders/{oid}/proof", {"image": "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + bytes([i]) * 64).decode()})
    calls_before = m.call_count
    oid = mkorder("TB-QX", proof=None)
    r = post(u, f"/api/orders/{oid}/proof", {"image": "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"9" * 64).decode()})
check("kuota habis: unggahan tetap 200 dan AI tidak dipanggil", r.status_code == 200 and m.call_count == calls_before
      and "proof_check" not in db.orders.find_one({"_id": ObjectId(oid)}))
# 15. hasil "Perlu dicek" boleh dicoba lagi (force); hasil lain tetap memakai cache
oU = mkorder("TB-U", proof=b"\xff\xd8\xff-foto-U")
with mock.patch.object(tb, "read_transfer_proof", return_value=dict(good, confidence=0.3, reference="REF313131")) as m:
    first = post(a, f"/api/orders/{oU}/proof/check").get_json()["order"]["proof_check"]
    post(a, f"/api/orders/{oU}/proof/check")
    check("hasil unclear tanpa force memakai cache", first["verdict"] == "unclear" and m.call_count == 1)
with mock.patch.object(tb, "read_transfer_proof", return_value=dict(good, reference="REF313131")) as m:
    again = post(a, f"/api/orders/{oU}/proof/check", {"force": True}).get_json()["order"]["proof_check"]
    check("force pada hasil unclear membaca ulang", again["verdict"] == "match" and m.call_count == 1)
    post(a, f"/api/orders/{oU}/proof/check", {"force": True})
    check("force pada hasil non-unclear tetap cache", m.call_count == 1)
    check("mode satu-baca: confirmed None, bukan False", again["confirmed"] is None)
# 16. server AI sibuk (503) -> otomatis memakai model cadangan; galat lain tidak
oF = mkorder("TB-F", proof=b"\xff\xd8\xff-foto-F")
busy = tb.ProofReadError("HTTP 503 dari API", status=503)
with mock.patch.object(tb, "PROOF_READER_FALLBACK_MODEL", "model-cadangan"), \
     mock.patch.object(tb, "read_transfer_proof", side_effect=[busy, dict(good, reference="REF515151")]) as m:
    r = post(a, f"/api/orders/{oF}/proof/check")
check("503 pada model utama -> berhasil lewat model cadangan",
      r.status_code == 200 and m.call_count == 2 and m.call_args_list[1].args[3] == "model-cadangan"
      and r.get_json()["order"]["proof_check"]["model"] == "model-cadangan")
oG = mkorder("TB-G", proof=b"\xff\xd8\xff-foto-G")
with mock.patch.object(tb, "PROOF_READER_FALLBACK_MODEL", "model-cadangan"), \
     mock.patch.object(tb, "read_transfer_proof", side_effect=tb.ProofReadError("HTTP 403 dari API", status=403)) as m:
    r = post(a, f"/api/orders/{oG}/proof/check")
check("galat 403 tidak memakai model cadangan", r.status_code == 502 and m.call_count == 1)
oH = mkorder("TB-H", proof=b"\xff\xd8\xff-foto-H")
with mock.patch.object(tb, "PROOF_READER_FALLBACK_MODEL", "model-cadangan"), \
     mock.patch.object(tb, "read_transfer_proof", side_effect=busy) as m:
    r = post(a, f"/api/orders/{oH}/proof/check")
check("kedua model sibuk -> 502 dengan pesan sibuk", r.status_code == 502 and m.call_count == 2 and "sibuk" in r.get_json()["error"].lower())

# ---- Bagian 17-23: lapisan akurasi (bacaan kedua, sidik jari, revisi, tanda edit, ukuran foto) ----
def fresh(code, ref, total=87500, **kw):
    return mkorder(code, total=total, proof=b"\xff\xd8\xff-" + code.encode(), **kw), dict(good, reference=ref)
with mock.patch.object(tb, "PROOF_CONFIRM_READ", True), mock.patch.object(tb, "PROOF_READER_FALLBACK_MODEL", "model-kedua"):
    # 17. dua bacaan sama -> terkonfirmasi, model kedua yang dipakai untuk bacaan kedua
    o, rd = fresh("TB-C1", "REF700001")
    with mock.patch.object(tb, "read_transfer_proof", side_effect=[rd, dict(rd)]) as m:
        pc = post(a, f"/api/orders/{o}/proof/check").get_json()["order"]["proof_check"]
    check("dua bacaan sama -> match terkonfirmasi", pc["verdict"] == "match" and pc["confirmed"] is True and pc["reads"] == 2)
    check("bacaan kedua memakai model lain", m.call_count == 2 and m.call_args_list[1].args[3] == "model-kedua")
    # 18. dua bacaan beda nominal -> diturunkan jadi Perlu dicek
    o, rd = fresh("TB-C2", "REF700002")
    with mock.patch.object(tb, "read_transfer_proof", side_effect=[rd, dict(rd, amount=78500)]):
        pc = post(a, f"/api/orders/{o}/proof/check").get_json()["order"]["proof_check"]
    check("dua bacaan beda -> unclear/inconsistent", pc["verdict"] == "unclear" and pc["reason"] == "inconsistent" and pc["disagree"] == ["nominal"])
    # 19. bacaan kedua gagal -> hasil tetap dipakai tetapi belum terkonfirmasi; verifikasi ulang (force) boleh
    o, rd = fresh("TB-C3", "REF700003")
    with mock.patch.object(tb, "read_transfer_proof", side_effect=[rd, tb.ProofReadError("HTTP 500", status=500)]) as m:
        pc = post(a, f"/api/orders/{o}/proof/check").get_json()["order"]["proof_check"]
    check("bacaan kedua gagal -> match belum terkonfirmasi", pc["verdict"] == "match" and pc["confirmed"] is False and pc["reads"] == 1)
    with mock.patch.object(tb, "read_transfer_proof", side_effect=[rd, dict(rd)]) as m:
        pc = post(a, f"/api/orders/{o}/proof/check", {"force": True}).get_json()["order"]["proof_check"]
        post(a, f"/api/orders/{o}/proof/check", {"force": True})
    check("force pada hasil belum terkonfirmasi membaca ulang sekali, lalu memakai cache", pc["confirmed"] is True and m.call_count == 2)
    # 19b. sisa waktu tidak cukup (unggah) -> bacaan kedua dilewati, tanpa memanggil AI lagi
    o, rd = fresh("TB-C4", "REF700004")
    with mock.patch.object(tb, "PROOF_CONFIRM_MIN_SECONDS", 999), mock.patch.object(tb, "read_transfer_proof", return_value=rd) as m:
        pc = post(a, f"/api/orders/{o}/proof/check").get_json()["order"]["proof_check"]
    check("waktu habis -> hanya satu bacaan", m.call_count == 1 and pc["confirmed"] is False)
    # 19c. hasil Perlu dicek tidak dibaca dua kali
    o, rd = fresh("TB-C5", "REF700005")
    with mock.patch.object(tb, "read_transfer_proof", return_value=dict(rd, confidence=0.3)) as m:
        post(a, f"/api/orders/{o}/proof/check")
    check("hasil unclear tidak memicu bacaan kedua", m.call_count == 1)

# 20. foto beda byte, referensi tak terbaca, nominal+menit sama -> pemakaian ulang
f1 = mkorder("TB-FP1", total=55500, proof=b"\xff\xd8\xff-fp-satu")
f2 = mkorder("TB-FP2", total=55500, proof=b"\xff\xd8\xff-fp-dua")
fp_read = dict(good, amount=55500, reference=None, time=datetime.strptime(wib(now - timedelta(minutes=8)), "%Y-%m-%d %H:%M"))
with mock.patch.object(tb, "read_transfer_proof", return_value=fp_read):
    p1 = post(a, f"/api/orders/{f1}/proof/check").get_json()["order"]["proof_check"]
    p2 = post(a, f"/api/orders/{f2}/proof/check").get_json()["order"]["proof_check"]
check("sidik jari pertama tersimpan, pesanan pertama cocok", p1["verdict"] == "match" and p1["fingerprint"].startswith("55500|"))
check("nominal+menit sama tanpa referensi -> suspicious", p2["verdict"] == "suspicious")

# Bagian kuota AI di atas sengaja mengunggah berkali-kali; kosongkan hitungan batas unggah supaya bagian di bawah tidak ikut terkena
db.rate_limits.delete_many({"_id": {"$regex": "^rl:proofup:"}})

# 21. foto diganti berkali-kali -> mencurigakan
r4 = mkorder("TB-REV", proof=b"\xff\xd8\xff-rev")
db.order_proofs.update_one({"_id": ObjectId(r4)}, {"$set": {"revision": 4}})
with mock.patch.object(tb, "read_transfer_proof", return_value=dict(good, reference="REF700021")):
    pc = post(a, f"/api/orders/{r4}/proof/check").get_json()["order"]["proof_check"]
check("revisi >= 4 -> suspicious/tampered", pc["verdict"] == "suspicious" and pc["reason"] == "tampered")
rn = mkorder("TB-REV1", proof=None)
r_first = post(u, f"/api/orders/{rn}/proof", {"image": "data:image/png;base64," + tiny_png})
rev1 = db.order_proofs.find_one({"_id": ObjectId(rn)})["revision"]
r_second = post(u, f"/api/orders/{rn}/proof", {"image": "data:image/png;base64," + other_png})
rev2 = db.order_proofs.find_one({"_id": ObjectId(rn)})["revision"]
check("nomor revisi unggahan: 1 lalu 2", r_first.status_code == 200 and r_second.status_code == 200 and (rev1, rev2) == (1, 2))

# 22. tanda edit dari AI -> mencurigakan
oe = mkorder("TB-EDIT", proof=b"\xff\xd8\xff-edit")
with mock.patch.object(tb, "read_transfer_proof", return_value=dict(good, reference="REF700023", edited=True, edit_note="nominal lebih tajam")):
    pc = post(a, f"/api/orders/{oe}/proof/check").get_json()["order"]["proof_check"]
check("tanda edit -> suspicious/tampered", pc["verdict"] == "suspicious" and pc["reason"] == "tampered")

# 23. foto bukti boleh lebih besar dari foto produk (resolusi lebih tinggi), tetapi tetap ada batasnya
ob = mkorder("TB-BIG", proof=None)
big = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"7" * 300_000).decode()            # ~400 ribu karakter: lolos batas bukti, melebihi batas foto biasa
check("foto bukti 400 ribu karakter diterima", post(u, f"/api/orders/{ob}/proof", {"image": "data:image/png;base64," + big}).status_code == 200)
huge = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"8" * 560_000).decode()            # ~750 ribu karakter: melebihi batas bukti
check("foto bukti di atas batas -> 422", post(u, f"/api/orders/{ob}/proof", {"image": "data:image/png;base64," + huge}).status_code == 422)

# 24. unggah dibatasi per akun per jam (melindungi penyimpanan, terpisah dari kuota baca AI)
db.rate_limits.delete_many({})
orl = mkorder("TB-RL", proof=None)
png_body = {"image": "data:image/png;base64," + tiny_png}
with mock.patch.object(tb, "read_transfer_proof", return_value=dict(good, reference="REF700099")):
    codes = [post(u, f"/api/orders/{orl}/proof", png_body).status_code for _ in range(tb.PROOF_UPLOADS_PER_HOUR + 2)]
check("unggah sampai batas per jam diterima", codes[:tb.PROOF_UPLOADS_PER_HOUR] == [200] * tb.PROOF_UPLOADS_PER_HOUR)
check("unggah melewati batas per jam -> 429", codes[-2:] == [429, 429])

# 25. akun dihapus -> foto bukti pesanannya ikut terhapus, foto milik akun lain tetap
master = mkuser("master1", "master")
victim = mkuser("korban", "user")
vo = ObjectId()
db.orders.insert_one({"_id": vo, "code": "TB-VIC", "user_id": victim, "username": "korban", "items": [], "subtotal": 1000,
    "shipping_fee": 0, "total": 1000, "payment_method": "transfer", "status": "completed",
    "created_at": now, "updated_at": now, "proof_at": now})
db.order_proofs.insert_one({"_id": vo, "image": b"\xff\xd8\xff-korban", "type": "image/jpeg", "uploaded_at": now})
keep = mkorder("TB-KEEP")
m = client("master1")
r = m.delete(f"/api/users/{victim}", json={}, headers={"X-CSRF-Token": m.csrf})
check("hapus akun berhasil (200)", r.status_code == 200)
check("foto bukti milik akun terhapus itu ikut dihapus", db.order_proofs.find_one({"_id": vo}) is None)
check("pesanannya tetap ada untuk pembukuan", db.orders.find_one({"_id": vo}) is not None)
check("foto bukti akun lain tidak tersentuh", db.order_proofs.find_one({"_id": ObjectId(keep)}) is not None)
check("audit menyebut jumlah foto dihapus", "1 foto bukti dihapus" in db.logs.find_one({"action": "user_hapus"})["detail"])

# 26. masa simpan: indeks TTL pada uploaded_at, aman dipanggil berulang
tb.ensure_ttl_index(db.order_proofs, "uploaded_at", tb.PROOF_RETENTION_DAYS, "proof_ttl")
tb.ensure_ttl_index(db.order_proofs, "uploaded_at", tb.PROOF_RETENTION_DAYS, "proof_ttl")
check("indeks TTL foto bukti terpasang", db.order_proofs.index_information()["proof_ttl"].get("expireAfterSeconds") == tb.PROOF_RETENTION_DAYS * 86400)

# 27. lama simpan dikirim ke frontend untuk pemberitahuan ke pelanggan
cfg = u.get("/api/auth/me").get_json()
check("lama simpan foto dikirim ke frontend", cfg["proof_retention_days"] == tb.PROOF_RETENTION_DAYS and cfg["proof_reader"] is True)

# 28. model menolak tingkat berpikir "medium" (HTTP 400): diulang dengan "low", bukan gagal total
db.rate_limits.delete_many({})
o28 = mkorder("TB-28", proof=b"\xff\xd8\xff-foto-28")
calls28 = []
def tolak_medium(image, mime, key, model, timeout=8, thinking="low"):
    calls28.append((model, thinking))
    if thinking == "medium":
        raise tb.ProofReadError("HTTP 400 dari API", status=400)
    return dict(good, reference="REF280028")
with mock.patch.object(tb, "read_transfer_proof", side_effect=tolak_medium):
    r = post(a, f"/api/orders/{o28}/proof/check")
check("medium ditolak (400) -> diulang low, hasil tersimpan (200)", r.status_code == 200 and "proof_check" in r.get_json()["order"])
check("urutan panggilan: medium lalu low pada model yang sama", calls28[:2] == [(tb.PROOF_READER_MODEL, "medium"), (tb.PROOF_READER_MODEL, "low")])

# 29. 400 pada mode low (mis. foto ditolak) tidak diulang-ulang
calls29 = []
def selalu_400(image, mime, key, model, timeout=8, thinking="low"):
    calls29.append(thinking)
    raise tb.ProofReadError("HTTP 400 dari API", status=400)
with mock.patch.object(tb, "read_transfer_proof", side_effect=selalu_400):
    try:
        tb.read_with_fallback(b"x", "image/png", 10, "low"); dilempar = False
    except tb.ProofReadError:
        dilempar = True
check("400 pada mode low: gagal apa adanya, hanya 1 panggilan", dilempar and calls29 == ["low"])

# 30. batas waktu unggah dibaca dari pengaturan (bukan angka mati)
db.rate_limits.delete_many({})
o30 = mkorder("TB-30", proof=None)
timeouts30 = []
def catat_timeout(image, mime, key, model, timeout=8, thinking="low"):
    timeouts30.append(timeout)
    return dict(good, reference="REF300030")
with mock.patch.object(tb, "PROOF_UPLOAD_TIMEOUT", 9), mock.patch.object(tb, "read_transfer_proof", side_effect=catat_timeout):
    r = post(u, f"/api/orders/{o30}/proof", png_body)
check("unggah memakai PROOF_UPLOAD_TIMEOUT dari pengaturan", r.status_code == 200 and timeouts30 and timeouts30[0] == 9)

# 31. model bawaan = dua model lite yang terbukti berhasil (bila tidak ditimpa .env)
import os
if not os.environ.get("PROOF_READER_MODEL") and not os.environ.get("PROOF_READER_FALLBACK_MODEL"):
    check("model bawaan: 3.5-flash-lite utama, 3.1-flash-lite cadangan", (tb.PROOF_READER_MODEL, tb.PROOF_READER_FALLBACK_MODEL) == ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite"))
print(f"\nSEMUA {ok} PEMERIKSAAN LOLOS")