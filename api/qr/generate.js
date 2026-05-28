const QRCode = require("qrcode");

module.exports = async function handler(req, res) {
  try {
    const payload = req.body || {};

    const expiredAt =
      payload.expired_at ||
      new Date(Date.now() + 30 * 60 * 1000).toISOString();

    const upstream = await fetch(`${process.env.API_BASE_URL}/qris/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        amount: payload.amount,
        expired_at: expiredAt,
        merchant_reff_no: payload.txn_id || undefined,
      }),
    });

    const json = await upstream.json();

    if (!upstream.ok) {
      return res.status(upstream.status).json(json);
    }

    const qris = json.data || json;
    const qrData = qris.qr_data;

    if (!qrData) {
      return res.status(500).json({
        ok: false,
        error: "QR data tidak ditemukan dari VPS",
        raw: json,
      });
    }

    const qrImage = await QRCode.toDataURL(qrData, {
      width: 320,
      margin: 1,
    });

    const active_qr = {
      mode: "vps",
      id: String(qris.id || qris.qris_id || ""),
      qr_id: String(qris.id || qris.qris_id || ""),
      txn_id: payload.txn_id || qris.reff_no || qris.merchant_reff_no || `TXN-${Date.now()}`,
      amount: Number(qris.amount || payload.amount || 0),
      qr_data: qrData,
      qr_image: qrImage,
      status: qris.status || "open",
      message: "QRIS generated via VPS",
      items: payload.items || [],
      customer_name: payload.customer_name || "",
      customer_email: payload.customer_email || "",
      cashier_name: payload.cashier_name || "Cashier",
      created_ts: Math.floor(Date.now() / 1000),
      raw: qris,
    };

    return res.status(200).json({
      ok: true,
      active_qr,
    });
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: err.message || "QR generate failed",
    });
  }
};