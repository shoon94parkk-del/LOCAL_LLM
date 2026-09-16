from pathlib import Path


class SkillStore:
    """Only skills installed under the explicitly configured directory are trusted."""
    def __init__(self, directory):
        self.root = Path(directory).resolve()

    def list(self):
        if not self.root.is_dir():
            return []
        return [{'name': p.parent.name} for p in sorted(self.root.glob('*/SKILL.md'))
                if p.resolve().is_relative_to(self.root)]

    def read(self, name):
        if name not in {s['name'] for s in self.list()}:
            raise ValueError('설치되지 않은 skill입니다')
        path = (self.root / name / 'SKILL.md').resolve()
        if not path.is_relative_to(self.root) or path.stat().st_size > 30000:
            raise ValueError('잘못된 skill 경로 또는 크기')
        return path.read_text(encoding='utf-8-sig')
