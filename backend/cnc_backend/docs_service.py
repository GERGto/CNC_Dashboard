from __future__ import annotations

import os


class DocsService:
    """Serves the repository's Markdown documentation to the dashboard UI.

    Only documents that appear in the generated index can be requested, so a
    document id can never escape the installation directory.
    """

    MAX_DOCUMENT_BYTES = 512 * 1024

    # Reading order of the guide. Everything not listed here is appended from
    # the scanned directories, so new documentation shows up without changes.
    ORDERED_DOCUMENTS = (
        ("README.md", "Übersicht"),
        ("docs/README.md", "Dokumentation"),
        ("docs/knowledge-base.md", "Dokumentation"),
        ("backend/README.md", "Backend"),
        ("docs/hardware/README.md", "Hardware"),
    )
    SCANNED_DIRECTORIES = (
        ("docs", "Dokumentation"),
        ("docs/hardware", "Hardware"),
    )

    def __init__(self, config):
        self.config = config

    @property
    def root_directory(self):
        return os.path.dirname(os.path.abspath(self.config.backend_root))

    def get_index(self):
        return {"documents": [self._describe(entry) for entry in self._collect_documents()]}

    def get_document(self, document_id):
        wanted = self._normalize_id(document_id)
        if not wanted:
            return None

        for entry in self._collect_documents():
            if entry["id"] != wanted:
                continue
            markdown = self._read_markdown(entry["path"])
            if markdown is None:
                return None
            return {**self._describe(entry), "markdown": markdown}
        return None

    def _collect_documents(self):
        root = self.root_directory
        documents = []
        seen = set()

        for relative_path, group in self.ORDERED_DOCUMENTS:
            full_path = os.path.join(root, relative_path.replace("/", os.sep))
            if os.path.isfile(full_path) and relative_path not in seen:
                seen.add(relative_path)
                documents.append({"id": relative_path, "path": full_path, "group": group})

        for directory, group in self.SCANNED_DIRECTORIES:
            directory_path = os.path.join(root, directory.replace("/", os.sep))
            if not os.path.isdir(directory_path):
                continue
            for name in sorted(os.listdir(directory_path)):
                if not name.lower().endswith(".md"):
                    continue
                relative_path = f"{directory}/{name}"
                if relative_path in seen:
                    continue
                full_path = os.path.join(directory_path, name)
                if not os.path.isfile(full_path):
                    continue
                seen.add(relative_path)
                documents.append({"id": relative_path, "path": full_path, "group": group})

        return documents

    def _describe(self, entry):
        return {
            "id": entry["id"],
            "group": entry["group"],
            "title": self._read_title(entry["path"], entry["id"]),
        }

    def _read_markdown(self, path):
        try:
            if os.path.getsize(path) > self.MAX_DOCUMENT_BYTES:
                return None
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except OSError:
            return None

    @staticmethod
    def _read_title(path, fallback_id):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                for _ in range(40):
                    line = handle.readline()
                    if not line:
                        break
                    stripped = line.strip()
                    if stripped.startswith("# "):
                        return stripped[2:].strip() or fallback_id
        except OSError:
            pass
        return os.path.basename(fallback_id)

    @staticmethod
    def _normalize_id(document_id):
        candidate = str(document_id or "").strip().replace("\\", "/")
        if not candidate or not candidate.lower().endswith(".md"):
            return ""
        return candidate
