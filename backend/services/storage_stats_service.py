"""Storage stats service — business logic for storage statistics."""
import os


def get_storage_stats_impl(upload_dir: str, output_dir: str, convert_dir: str, db_path: str) -> dict:
    """Get storage statistics for all directories and database."""
    def _dir_size(path: str) -> int:
        total_bytes = 0
        if not os.path.exists(path):
            return 0
        for dirpath, _, filenames in os.walk(path):
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                if os.path.isfile(fp):
                    total_bytes += os.path.getsize(fp)
        return total_bytes

    uploads_size = _dir_size(upload_dir)
    outputs_size = _dir_size(output_dir)
    converted_size = _dir_size(convert_dir)
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    return {
        "uploads": uploads_size,
        "outputs": outputs_size,
        "converted": converted_size,
        "database": db_size,
        "total": uploads_size + outputs_size + converted_size + db_size,
    }
