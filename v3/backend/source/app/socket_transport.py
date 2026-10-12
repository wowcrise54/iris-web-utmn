"""Native ASGI Socket.IO preserving IRIS's synchronous event handlers."""
import asyncio
import inspect
import socketio
from starlette.concurrency import run_in_threadpool
from .web import current_app, request

class Namespace(socketio.AsyncNamespace):
    async def trigger_event(self, event, *args):
        handler = getattr(self, 'on_' + event, None)
        if handler is not None:
            return await self._transport.dispatch(event, handler, args[0], *args[1:], namespace=self.namespace)

class _TransportApp(socketio.ASGIApp):
    def __init__(self, transport):
        self.transport = transport
        super().__init__(transport.server, other_asgi_app=transport.app)

    async def __call__(self, scope, receive, send):
        self.transport.loop = asyncio.get_running_loop()
        await super().__call__(scope, receive, send)

class SocketIO:
    def __init__(self, app, cors_allowed_origins=None, message_queue=None, **kwargs):
        self.app = app
        self.loop = None
        self.queue = message_queue
        self.publisher = None
        manager = socketio.AsyncAioPikaManager(message_queue, channel='iris-socketio') if message_queue else None
        self.server = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins=cors_allowed_origins,
                                           client_manager=manager)
        self.asgi_app = _TransportApp(self)
        app.extensions['socketio'] = self

    async def dispatch(self, event, handler, sid, *args, namespace='/'):
        self.loop = asyncio.get_running_loop()
        environ = self.server.get_environ(sid, namespace=namespace)
        if environ is None:
            return False if event == 'connect' else None
        if event == 'connect' and args and isinstance(args[0], dict):
            args = args[1:]
        expected = inspect.signature(handler).parameters
        if event == 'connect' and expected and not args:
            args = (None,)
        args = args[:len(expected)]
        def invoke():
            with self.app.request_context(environ):
                request.sid = sid
                request.namespace = namespace
                request.event = {'message': event, 'args': args}
                return handler(*args)
        return await run_in_threadpool(invoke)

    def on_namespace(self, namespace):
        namespace._transport = self
        self.server.register_namespace(namespace)

    def on(self, event, namespace=None):
        selected = namespace or '/'
        def decorate(handler):
            async def invoke(sid, *args):
                return await self.dispatch(event, handler, sid, *args, namespace=selected)
            self.server.on(event, handler=invoke, namespace=selected)
            return handler
        return decorate

    def on_event(self, event, handler, namespace=None):
        return self.on(event, namespace)(handler)

    def _submit(self, coroutine):
        if self.loop is None or not self.loop.is_running():
            coroutine.close()
            return None
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result()

    def emit(self, event, data=None, *, to=None, room=None, skip_sid=None, namespace=None,
             broadcast=False, include_self=True, **kwargs):
        namespace = namespace or '/'
        if self.loop is None or not self.loop.is_running():
            if self.queue:
                from app.socket_io_queue import SocketIOKombuManager
                if self.publisher is None:
                    self.publisher = SocketIOKombuManager(self.queue, channel='iris-socketio', write_only=True)
                return self.publisher.emit(event, data, namespace=namespace, room=to or room, skip_sid=skip_sid)
            return None
        return self._submit(self.server.emit(event, data, to=to or room, skip_sid=skip_sid, namespace=namespace))

    def enter_room(self, sid, room, namespace=None):
        return self._submit(self.server.enter_room(sid, room, namespace=namespace or '/'))

    def leave_room(self, sid, room, namespace=None):
        return self._submit(self.server.leave_room(sid, room, namespace=namespace or '/'))

    def start_background_task(self, target, *args, **kwargs):
        async def run():
            return await run_in_threadpool(target, *args, **kwargs)
        return asyncio.run_coroutine_threadsafe(run(), self.loop)

    def sleep(self, seconds=0):
        import time
        time.sleep(seconds)

    def stop(self):
        return self._submit(self.server.shutdown())

def emit(event, data=None, *, to=None, room=None, skip_sid=None, namespace=None,
         broadcast=False, include_self=True, **kwargs):
    transport = current_app.extensions['socketio']
    selected = namespace or request.namespace
    destination = to or room
    if destination is None and not broadcast:
        destination = request.sid
    if not include_self and skip_sid is None:
        skip_sid = request.sid
    return transport.emit(event, data, to=destination, skip_sid=skip_sid, namespace=selected, **kwargs)

def join_room(room, sid=None, namespace=None):
    return current_app.extensions['socketio'].enter_room(sid or request.sid, room, namespace or request.namespace)

def leave_room(room, sid=None, namespace=None):
    return current_app.extensions['socketio'].leave_room(sid or request.sid, room, namespace or request.namespace)
