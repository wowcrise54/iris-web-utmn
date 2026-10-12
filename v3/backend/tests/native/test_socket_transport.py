"""Socket.IO retains HTTP handshake, room delivery and request identity."""
import asyncio
import importlib.util
import sys
import threading
import types
from pathlib import Path

import httpx
import aiohttp
import pytest
import socketio
import uvicorn


ROOT = Path(__file__).resolve().parents[2] / "source" / "app"


@pytest.mark.parametrize("protocol", ["polling", "websocket"])
def test_socketio_room_delivery_uses_signed_session(protocol):
    assert (ROOT / "socket_transport.py").exists(), "Native ASGI Socket.IO integration missing"
    name = "_iris_socket_contract"
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT)]
    sys.modules[name] = package
    for module in ("web", "socket_transport"):
        spec = importlib.util.spec_from_file_location(f"{name}.{module}", ROOT / f"{module}.py")
        instance = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = instance
        spec.loader.exec_module(instance)
    web = sys.modules[f"{name}.web"]
    transport = sys.modules[f"{name}.socket_transport"]
    app = web.IRISApp(__name__)
    app.config.update(SECRET_KEY="socket-test", SESSION_COOKIE_SECURE=False)
    sio = transport.SocketIO(app)

    @sio.on("join")
    def join(data):
        transport.join_room(data["room"])
        transport.emit("joined", {"user": web.session["user"], "room": data["room"]}, room=data["room"])
        return {"ok": True}

    @app.route("/notify", methods=["POST"])
    def notify():
        sio.emit("notification", {"value": 42}, room="case-5")
        return "ok"

    @app.route("/updater-handoff", methods=["POST"])
    def updater_handoff():
        sio.stop()
        return "updater started"

    async def exercise():
        import socket
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.close()
        config = uvicorn.Config(sio.asgi_app, host="127.0.0.1", port=port, log_level="error", lifespan="off")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        http_session = aiohttp.ClientSession()
        client = socketio.AsyncClient(http_session=http_session)
        try:
            for _ in range(100):
                if server.started:
                    break
                await asyncio.sleep(.02)
            assert server.started
            serializer = app.session_interface.get_signing_serializer(app)
            cookie = serializer.dumps({"user": "analyst"})
            joined = asyncio.Event()
            notified = asyncio.Event()
            result = {}

            @client.on("joined")
            def on_join(data):
                result.update(data)
                joined.set()

            @client.on("notification")
            def on_notify(data):
                result.update(data)
                notified.set()

            await client.connect(f"http://127.0.0.1:{port}", headers={"Cookie": f"session={cookie}"}, transports=[protocol])
            assert await client.call("join", {"room": "case-5"}) == {"ok": True}
            await asyncio.wait_for(joined.wait(), 5)
            assert result == {"user": "analyst", "room": "case-5"}
            async with httpx.AsyncClient(trust_env=False) as http:
                response = await http.post(f"http://127.0.0.1:{port}/notify")
                assert response.status_code == 200, (dict(response.headers), response.text)
            await asyncio.wait_for(notified.wait(), 5)
            assert result["value"] == 42
            async with httpx.AsyncClient(trust_env=False) as http:
                handoff = await http.post(f"http://127.0.0.1:{port}/updater-handoff")
                assert handoff.status_code == 200
                assert handoff.text == "updater started"
        finally:
            if client.connected:
                await client.disconnect()
            # Polling may leave a pending long poll after the disconnect packet.
            # Dispose that client task before closing its explicitly owned session.
            if client.eio.read_loop_task:
                client.eio.read_loop_task.cancel()
                await asyncio.gather(client.eio.read_loop_task, return_exceptions=True)
            await http_session.close()
            server.should_exit = True
            await asyncio.to_thread(thread.join, 5)

    asyncio.run(exercise())
