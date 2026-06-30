from dataclasses import dataclass, field


@dataclass
class ChangeSet:
    files_added: dict = field(default_factory=dict)
    files_modified: dict = field(default_factory=dict)
    files_deleted: dict = field(default_factory=dict)
    reg_added: dict = field(default_factory=dict)
    reg_modified: dict = field(default_factory=dict)
    reg_deleted: dict = field(default_factory=dict)

    def total_files(self) -> int:
        return len(self.files_added) + len(self.files_modified) + len(self.files_deleted)

    def total_reg(self) -> int:
        return len(self.reg_added) + len(self.reg_modified) + len(self.reg_deleted)


def diff_files(fs_before: dict, fs_after: dict):
    """Returns (added, modified, deleted) for two filesystem snapshots."""
    added, modified, deleted = {}, {}, {}
    for path in set(fs_before) | set(fs_after):
        if path not in fs_before:
            added[path] = fs_after[path]
        elif path not in fs_after:
            deleted[path] = fs_before[path]
        else:
            b, a = fs_before[path], fs_after[path]
            if b.get("md5") != a.get("md5") or b.get("size") != a.get("size"):
                modified[path] = {"before": b, "after": a}
    return added, modified, deleted


def diff_registry(reg_before: dict, reg_after: dict):
    """Returns (added, modified, deleted) for two registry snapshots."""
    added, modified, deleted = {}, {}, {}
    for key in set(reg_before) | set(reg_after):
        if key not in reg_before:
            added[key] = reg_after[key]
        elif key not in reg_after:
            deleted[key] = reg_before[key]
        else:
            if reg_before[key].get("data") != reg_after[key].get("data"):
                modified[key] = {"before": reg_before[key], "after": reg_after[key]}
    return added, modified, deleted


def assemble(file_triple, reg_triple) -> ChangeSet:
    """Build a ChangeSet from (added, modified, deleted) file + registry triples."""
    fa, fm, fd = file_triple
    ra, rm, rd = reg_triple
    return ChangeSet(
        files_added=fa, files_modified=fm, files_deleted=fd,
        reg_added=ra, reg_modified=rm, reg_deleted=rd,
    )


def diff(before: dict, after: dict) -> ChangeSet:
    """Backward-compatible whole-snapshot diff (walk engine / v1 sessions)."""
    return assemble(
        diff_files(before.get("filesystem", {}), after.get("filesystem", {})),
        diff_registry(before.get("registry", {}), after.get("registry", {})),
    )
