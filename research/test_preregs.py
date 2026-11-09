import hashlib
import re
import unittest
from pathlib import Path

D = Path(__file__).resolve().parent / "preregs"
MARK = b"<!-- body -->\n"


def body_sha(b):
    return hashlib.sha256(b[b.index(MARK) + len(MARK):]).hexdigest()


class PreregHashes(unittest.TestCase):
    def test_every_signed_file_matches_its_recorded_hashes(self):
        readme = body_sha((D / "README.md").read_bytes())
        files = sorted(D.glob("R3-*.md"))
        self.assertEqual(len(files), 6)
        for f in files:
            b = f.read_bytes()
            head = b[:b.index(MARK)].decode()
            self.assertIn(body_sha(b), head, f.name)
            self.assertIn(readme, head, f.name)
            m = re.search(r"amended prereg `([^`]+)` \(whole file\): `([0-9a-f]{64})`", head)
            if "amendment" in f.name:
                self.assertEqual(hashlib.sha256((D / m.group(1)).read_bytes()).hexdigest(), m.group(2), f.name)
                self.assertIn("Prior knowledge", b.decode())


if __name__ == "__main__":
    unittest.main()
