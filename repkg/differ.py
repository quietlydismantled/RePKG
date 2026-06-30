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


def diff(before: dict, after: dict) -> ChangeSet:
    fs_before = before.get("filesystem", {})
    fs_after = after.get("filesystem", {})
    reg_before = before.get("registry", {})
    reg_after = after.get("registry", {})

    cs = ChangeSet()

    all_files = set(fs_before) | set(fs_after)
    for path in all_files:
        if path not in fs_before:
            cs.files_added[path] = fs_after[path]
        elif path not in fs_after:
            cs.files_deleted[path] = fs_before[path]
        else:
            b, a = fs_before[path], fs_after[path]
            if b.get("md5") != a.get("md5") or b.get("size") != a.get("size"):
                cs.files_modified[path] = {"before": b, "after": a}

    all_reg = set(reg_before) | set(reg_after)
    for key in all_reg:
        if key not in reg_before:
            cs.reg_added[key] = reg_after[key]
        elif key not in reg_after:
            cs.reg_deleted[key] = reg_before[key]
        else:
            if reg_before[key].get("data") != reg_after[key].get("data"):
                cs.reg_modified[key] = {"before": reg_before[key], "after": reg_after[key]}

    return cs
