"""Entry point for the NFCorpus diagnostics workbench."""
import os
from app.main import app

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "10000"))
    app.run(host=host, port=port, debug=False)
