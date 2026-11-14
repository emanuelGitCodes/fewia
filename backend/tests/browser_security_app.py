import os
from html import escape

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

os.environ["FEWIA_AUTH_MODE"] = "local_demo"
os.environ["FEWIA_PUBLIC_ORIGIN"] = "http://127.0.0.1:49121"
os.environ["FEWIA_DATABASE_MODE"] = "local"
os.environ["FEWIA_TRANSPORT_MODE"] = "local"

from app.main import BrowserPolicyMiddleware  # noqa: E402

TARGETS = {
    "apply": "/grocery/proposals/synthetic-proposal/apply",
    "discard": "/grocery/proposals/synthetic-proposal/discard",
    "cart": "/grocery/kroger/cart/add",
    "connect": "/grocery/kroger/connect",
    "signout": "/grocery/signout",
}


class ObserveBrowserHeaders:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_headers = Headers(scope=scope)

        async def send_observed(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                for name in (
                    "origin",
                    "sec-fetch-site",
                    "sec-fetch-mode",
                    "sec-fetch-dest",
                ):
                    value = request_headers.get(name)
                    if value is not None:
                        response_headers[f"x-fewia-test-{name}"] = value
            await send(message)

        await self.app(scope, receive, send_observed)


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(BrowserPolicyMiddleware)
app.add_middleware(ObserveBrowserHeaders)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


def form_document(target: str) -> HTMLResponse:
    path = TARGETS.get(target)
    if path is None:
        raise HTTPException(status_code=404)
    action = escape(f"http://127.0.0.1:49121/api{path}", quote=True)
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><title>FEWIA form probe</title>'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<link rel="icon" href="data:,">'
        "</head><body><h1>Browser form probe</h1>"
        f'<form method="post" action="{action}">'
        '<input name="confirm" value="true" type="hidden">'
        '<button type="submit">Submit form</button></form></body></html>'
    )


@app.get("/attacker", response_class=HTMLResponse)
async def attacker(target: str = "apply") -> HTMLResponse:
    return form_document(target)


@app.get("/grocery/security/document", response_class=HTMLResponse)
async def browser_document(target: str = "apply") -> HTMLResponse:
    return form_document(target)


async def sentinel(request: Request) -> dict[str, object]:
    return {"sentinel": "accepted", "path": request.url.path}


for target_path in TARGETS.values():
    app.add_api_route(target_path, sentinel, methods=["POST"])
