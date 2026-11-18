"""Entry point aplikasi TokoBiru (dipakai lokal, Vercel, dan tes)."""
import os
from tokobiru import *  # noqa: F401,F403
from tokobiru import _env_int, _env_str, create_app, smtplib  # noqa: F401

app = create_app()

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
