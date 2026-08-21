from watchdog.events import FileSystemEventHandler

from notes import is_markdown
from sync import deindex_note, safe_index


class VaultHandler(FileSystemEventHandler):
    """Shared watcher: indexes on create/modify, deindexes on delete, and treats moves as delete+create."""
    def __init__(self, collection, route_func, name):
        self.collection = collection
        self.route_func = route_func
        self.name = name
        super().__init__()

    def _index(self, file_path):
        safe_index(self.route_func, file_path, self.collection, self.name)

    def on_created(self, event):
        if not event.is_directory: self._index(event.src_path)

    def on_modified(self, event):
        if not event.is_directory: self._index(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory and is_markdown(event.src_path):
            deindex_note(event.src_path, self.collection)

    def on_moved(self, event):
        if not event.is_directory:
            if is_markdown(event.src_path):
                deindex_note(event.src_path, self.collection)
            self._index(event.dest_path)
