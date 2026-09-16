import asyncio
import json

from app.config import settings
from app.db import Database
from app.llm import MockLLM, PlaywrightGLM
from app.memory import MemoryStore
from app.reflection import run_reflection


async def main() -> None:
    memory = MemoryStore(Database(settings.db_path))
    llm = PlaywrightGLM(settings) if settings.glm_mode.lower() == "playwright" else MockLLM()
    result = await run_reflection(memory, llm, limit=100)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
