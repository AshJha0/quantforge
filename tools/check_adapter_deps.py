#!/usr/bin/env python3
"""The numerical libraries never depend on the K-3 adapters (specifications/12-platform/adapters.md section 4,
KR-281; ADR-0006). Standard library only.

Fails if a file in a library source tree imports or includes an adapter or infrastructure client module, or a
library manifest names one. `--self-test` first plants one forbidden import and one forbidden manifest entry in
a temporary tree and requires both to be reported (plan 14.10 rule 1).

    python tools/check_adapter_deps.py [--self-test] [ROOT]
"""

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PY_MODULES = (
    "quantforge_adapters",
    "grpc",
    "pyarrow",
    "kafka",
    "confluent_kafka",
    "psycopg",
    "psycopg2",
    "pg8000",
    "clickhouse_connect",
    "clickhouse_driver",
    "prometheus_client",
    "aeron",
)
JAVA_PACKAGES = (
    "io.aeron",
    "org.agrona",
    "org.apache.kafka",
    "io.grpc",
    "org.postgresql",
    "com.clickhouse",
    "io.prometheus",
    "org.apache.arrow",
    "org.quantforge.k3",
)
RUST_CRATES = (
    "tonic",
    "rdkafka",
    "kafka",
    "postgres",
    "tokio-postgres",
    "sqlx",
    "clickhouse",
    "prometheus",
    "arrow",
    "arrow-flight",
    "aeron-rs",
    "grpcio",
    "prost",
)
CPP_NAMES = ("rdkafka", "librdkafka", "libpq", "pqxx", "grpc", "aeron", "clickhouse", "prometheus", "arrow")

PY_RE = re.compile(r"^\s*(?:import|from)\s+(" + "|".join(PY_MODULES) + r")\b", re.MULTILINE)
JAVA_RE = re.compile(
    r"^\s*import\s+(?:static\s+)?(" + "|".join(re.escape(p) for p in JAVA_PACKAGES) + r")\b", re.MULTILINE
)
RUST_USE_RE = re.compile(
    r"^\s*(?:pub\s+)?(?:use|extern\s+crate)\s+("
    + "|".join(c.replace("-", "_") for c in RUST_CRATES)
    + r")\b",
    re.MULTILINE,
)
CPP_INC_RE = re.compile(
    r"^\s*#\s*include\s*[<\"](?:[^>\"]*/)?(" + "|".join(CPP_NAMES) + r")[^>\"]*[>\"]", re.MULTILINE
)
CMAKE_RE = re.compile(
    r"(?:find_package|pkg_check_modules|target_link_libraries)\s*\(([^)]*)\)", re.IGNORECASE
)
POM_RE = re.compile(r"<groupId>\s*(" + "|".join(re.escape(p) for p in JAVA_PACKAGES) + r")[^<]*</groupId>")


def _files(root: Path, sub: str, pattern: str) -> list[Path]:
    base = root / sub
    if not base.exists():
        return []
    return sorted(
        p
        for p in base.rglob(pattern)
        if "target" not in p.parts and "build" not in p.parts and ".venv" not in p.parts
    )


def _pyproject_deps(text: str) -> list[str]:
    m = re.search(r"^\[project\][^\[]*?^dependencies\s*=\s*\[(.*?)\]", text, re.MULTILINE | re.DOTALL)
    if not m:
        return []
    return [
        re.split(r"[\s<>=!~;\[]", d.strip().strip("\"'"), maxsplit=1)[0].lower()
        for d in m.group(1).split(",")
        if d.strip()
    ]


def _cargo_deps(text: str) -> list[str]:
    names = []
    section = ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            section = s
            if re.match(r"\[(?:.*\.)?(?:dev-|build-)?dependencies\.([A-Za-z0-9_-]+)\]", s):
                names.append(s.rsplit(".", 1)[1].rstrip("]"))
            continue
        if re.match(r"\[(?:.*\.)?(?:dev-|build-)?dependencies\]", section):
            m = re.match(r"([A-Za-z0-9_-]+)\s*=", s)
            if m:
                names.append(m.group(1))
    return names


def check(root: Path) -> list[str]:
    bad: list[str] = []

    def rel(p: Path) -> str:
        return p.relative_to(root).as_posix()

    for sub in ("python/quantforge_core", "python/quantforge_research"):
        for p in _files(root, sub, "*.py"):
            for m in PY_RE.finditer(p.read_text(encoding="utf-8", errors="replace")):
                bad.append(f"{rel(p)}: imports {m.group(1)}")
    for p in _files(root, "java25/src", "*.java"):
        for m in JAVA_RE.finditer(p.read_text(encoding="utf-8", errors="replace")):
            bad.append(f"{rel(p)}: imports {m.group(1)}")
    for p in _files(root, "rust", "*.rs"):
        for m in RUST_USE_RE.finditer(p.read_text(encoding="utf-8", errors="replace")):
            bad.append(f"{rel(p)}: uses crate {m.group(1)}")
    for ext in ("*.h", "*.hpp", "*.cpp", "*.cc", "*.ixx", "*.cppm"):
        for p in _files(root, "cpp26", ext):
            for m in CPP_INC_RE.finditer(p.read_text(encoding="utf-8", errors="replace")):
                bad.append(f"{rel(p)}: includes {m.group(1)}")
    # Manifests.
    pyproject = root / "python" / "pyproject.toml"
    if pyproject.exists():
        forbidden = {m.replace("_", "-") for m in PY_MODULES} | {
            "quantforge-adapters",
            "grpcio",
            "kafka-python",
            "psycopg-binary",
        }
        for dep in _pyproject_deps(pyproject.read_text(encoding="utf-8")):
            if dep.replace("_", "-") in forbidden:
                bad.append(f"python/pyproject.toml: dependency {dep}")
    for p in _files(root, "rust", "Cargo.toml"):
        for dep in _cargo_deps(p.read_text(encoding="utf-8")):
            if dep in RUST_CRATES or dep.replace("_", "-") in RUST_CRATES:
                bad.append(f"{rel(p)}: dependency {dep}")
    pom = root / "java25" / "pom.xml"
    if pom.exists():
        for m in POM_RE.finditer(pom.read_text(encoding="utf-8")):
            bad.append(f"java25/pom.xml: dependency group {m.group(1)}")
    for p in _files(root, "cpp26", "CMakeLists.txt"):
        for m in CMAKE_RE.finditer(p.read_text(encoding="utf-8", errors="replace")):
            for word in re.findall(r"[A-Za-z0-9_:+.-]+", m.group(1)):
                if word.lower().split("::")[0] in CPP_NAMES:
                    bad.append(f"{rel(p)}: links {word}")
    return bad


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        files = {
            "python/quantforge_core/ok.py": "import json\nfrom quantforge_core import rng\n",
            "python/pyproject.toml": '[project]\nname = "x"\ndependencies = ["numpy>=2.0"]\n',
            "java25/src/main/java/A.java": "import java.util.List;\n",
            "java25/pom.xml": "<groupId>org.junit.jupiter</groupId>\n",
            "rust/Cargo.toml": '[dependencies]\nserde = "1"\n',
            "rust/src/lib.rs": "use std::fmt;\n",
            "cpp26/CMakeLists.txt": "find_package(Threads)\n",
            "cpp26/src/a.cpp": "#include <vector>\n",
        }
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text, encoding="utf-8")
        if check(root):
            raise SystemExit(f"self-test: clean tree reported {check(root)}")
        plants = {
            "python/quantforge_core/ok.py": "import json\nimport grpc\n",
            "python/pyproject.toml": '[project]\nname = "x"\ndependencies = ["numpy>=2.0", "pg8000==1.31.6"]\n',
            "java25/src/main/java/A.java": "import io.aeron.Aeron;\n",
            "java25/pom.xml": "<groupId>org.apache.kafka</groupId>\n",
            "rust/Cargo.toml": '[dependencies]\nserde = "1"\nrdkafka = "0.36"\n',
            "rust/src/lib.rs": "use tonic::transport;\n",
            "cpp26/CMakeLists.txt": "find_package(Arrow REQUIRED)\n",
            "cpp26/src/a.cpp": "#include <librdkafka/rdkafkacpp.h>\n",
        }
        for name, text in plants.items():
            (root / name).write_text(text, encoding="utf-8")
            found = check(root)
            if len(found) != 1:
                raise SystemExit(f"self-test: planted {name} gave {found}")
            (root / name).write_text(files[name], encoding="utf-8")
    print(f"self-test: {len(plants)} planted forbidden dependencies each reported, clean tree passes")


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        self_test()
        argv = [a for a in argv if a != "--self-test"]
        if not argv:
            return 0
    root = Path(argv[0]) if argv else ROOT
    bad = check(root)
    for b in bad:
        print(f"ADAPTER_DEP {b}")
    print(f"library trees: {len(bad)} adapter dependencies")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
