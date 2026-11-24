'''Minimal stub of FastAPI components used by the project when the real FastAPI package is unavailable.'''

class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")

class Request:
    async def json(self):
        return {}

class BackgroundTasks:
    def __init__(self):
        self._tasks = []
    def add_task(self, func, *args, **kwargs):
        # Store the callable to be executed later (synchronously for the stub)
        self._tasks.append((func, args, kwargs))
    async def __call__(self):
        for func, args, kwargs in self._tasks:
            # In the stub we simply call the function directly; if it is async we run it via asyncio
            result = func(*args, **kwargs)
            if hasattr(result, "__await__"):
                import asyncio
                await result

class UploadFile:
    def __init__(self, filename: str = ""):
        self.filename = filename
        self.file = None
    async def read(self):
        return b""

def File(...):  # placeholder for FastAPI's File dependency marker
    return None

class FastAPI:
    def __init__(self, title: str = "", version: str = ""):
        self.title = title
        self.version = version
        self.routes = []
    def add_middleware(self, *args, **kwargs):
        pass
    def post(self, path: str):
        def decorator(func):
            # simply register the function; no real routing needed for tests
            self.routes.append(("POST", path, func))
            return func
        return decorator
