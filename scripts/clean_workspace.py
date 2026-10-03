"""Clean Nomad AGY Workspace Subfolders Safely.

Safety Rules:
- Only ever deletes subfolders inside AGY_WORKSPACE_ROOT (Desktop/test).
- NEVER deletes the workspace root itself.
- Validates path boundaries before deletion.
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.loop.workspace import (
    get_default_workspace_root,
    clean_loop_workspace,
    is_path_inside_workspace,
)


def main():
    parser = argparse.ArgumentParser(description="Safely clean Nomad loop workspace subfolders")
    parser.add_argument("--run", type=str, help="Specific loop run ID or subfolder name to clean")
    parser.add_argument("--all-test-runs", action="store_true", help="Clean all 'run_*' test subfolders in workspace root")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be deleted without deleting")
    args = parser.parse_args()

    root = get_default_workspace_root()
    print(f"[*] Workspace Root: {root}")

    if not root.exists():
        print("[-] Workspace root does not exist. Nothing to clean.")
        return

    if not args.run and not args.all_test_runs:
        print("[-] Please specify --run <id> or --all-test-runs")
        parser.print_help()
        sys.exit(1)

    if args.run:
        target = root / args.run
        if not target.exists():
            # Try searching with run_ prefix or loop_run_id match
            matches = list(root.glob(f"*{args.run}*"))
            if matches:
                target = matches[0]
            else:
                print(f"[-] Subfolder for run '{args.run}' not found in {root}")
                return

        if not is_path_inside_workspace(target, root) or target.resolve() == root.resolve():
            print(f"[!] Safety violation: {target} is not a valid subfolder of {root}")
            sys.exit(1)

        if args.dry_run:
            print(f"[DRY-RUN] Would delete: {target}")
        else:
            success = clean_loop_workspace(args.run, base_root=root)
            if success:
                print(f"[+] Successfully deleted: {target}")
            else:
                print(f"[-] Failed to clean: {target}")

    if args.all_test_runs:
        subfolders = [p for p in root.iterdir() if p.is_dir() and p.name.startswith("run_")]
        if not subfolders:
            print("[*] No 'run_*' subfolders found.")
            return

        print(f"[*] Found {len(subfolders)} test subfolder(s).")
        for sub in subfolders:
            if not is_path_inside_workspace(sub, root) or sub.resolve() == root.resolve():
                print(f"[!] Skipping unsafe path: {sub}")
                continue
            if args.dry_run:
                print(f"[DRY-RUN] Would delete: {sub}")
            else:
                import shutil
                shutil.rmtree(sub, ignore_errors=True)
                print(f"[+] Deleted: {sub}")


if __name__ == "__main__":
    main()
