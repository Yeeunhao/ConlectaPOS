🚀 *Conlecta 1.1* — Release Notes
📅 May 2026 | v1.0 → v1.1

Halo tim! Update besar Conlecta 1.1 sudah siap — fokus ke *role admin*, *multi-kasir*, *QR display*, dan *tip per item*.

━━━━━━━━━━━━━━━━━━━━

✨ *HIGHLIGHTS*

• Merchant admin vs kasir — hak akses jelas
• Session per kasir/device — QR & upload tidak bentrok
• QR display lebih stabil — tidak flicker & ada notif bayar
• Tip Rp per item — masuk total, PDF merchant & vendor pisah tip

━━━━━━━━━━━━━━━━━━━━

🆕 *FITUR BARU*

*1. Merchant Admin & Kasir*
• Akun bisa di-set sebagai *merchant admin*
• Admin: edit stok, kelola vendor, buka Analytics
• Kasir: fokus checkout saja — stok view-only, Analytics disembunyikan
• Tambah/edit/hapus vendor hanya untuk admin

*2. Vendor per Merchant*
• Data vendor per toko (merchant)
• Bug save/delete vendor sudah diperbaiki
• Dropdown vendor langsung update setelah tambah

*3. Tip Rp per Item*
• Field *Tip Rp* di cart, sebelah Disc %
• Total baris = (harga × qty − diskon) + tip
• History, receipt email & layar pelanggan: tip sudah masuk total baris (bukan baris terpisah)
• PDF merchant & vendor: harga normal di atas, *+ tip Rp …* di bawah

*4. Multi-Kasir & Device*
• QR aktif per kasir/device, tidak shared antar staff
• Icon bayar & video custom per device
• Log terfilter per akun & device
• Data browser tidak bocor antar login di PC yang sama

*5. QR Display & Checkout*
• Theme QR display dikunci setelah buka — tidak ganti-ganti
• Notif sukses bayar & dismiss ~6 detik
• Dismiss QR tidak hapus cart & data pelanggan
• Bayar cash → field uang diterima ikut clear
• Login sukses → refresh halaman (stok merchant lama tidak nyangkut)
• QR tetap muncul dari qr_data kalau qr_image kosong (fix Vercel)

*6. Tampilan & Theme*
• Background canvas satu layer — tidak dobel/berkedip
• Animasi theme berbeda per pilihan theme

━━━━━━━━━━━━━━━━━━━━

🔧 *PERBAIKAN*

• Registrasi PIN tidak stuck lagi setelah input PIN
• Multi login session — beberapa kasir/device bisa login bersamaan
• System admin bisa di-set lewat env CONLECTA_SYSTEM_ADMIN_EMAILS
• OAuth Gmail & Sheets dari token.json / oauth_token.json
• Stok selalu refresh saat login — tidak merge data lama

━━━━━━━━━━━━━━━━━━━━

👤 *Untuk Merchant Admin*
✅ Atur siapa admin vs kasir
✅ Kelola vendor & lihat invoice vendor (PDF ada breakdown tip)
✅ Set theme QR Display di Settings

🛒 *Untuk Kasir*
✅ Pakai Disc %, Disc Rp, Tip Rp, Free per item
✅ QR kamu sendiri — tidak bentrok dengan kasir lain
✅ Dismiss QR = cart tetap ada
✅ Tidak ada tab Analytics, stok cuma lihat

━━━━━━━━━━━━━━━━━━━━

📦 *CARA UPDATE*

1️⃣ Deploy frontend (Vercel)
2️⃣ Restart backend VPS (wajib — migration tip_amount)
3️⃣ Kasir refresh browser setelah deploy

Transaksi lama aman — tip lama = Rp 0.

━━━━━━━━━━━━━━━━━━━━

Pertanyaan atau ada bug setelah update? Langsung hubungi tim dev 🙏

— Conlecta POS Team
