import os
import shutil
import zipfile
import tarfile
from typing import Optional

class FileManager:
    """
    Utility class to abstract away file system operations (zipping, extracting, moving, sizing) 
    from business logic in views and tasks.
    """

    @staticmethod
    def create_dir(path: str) -> str:
        """Ensure a directory exists."""
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def remove_dir(path: str) -> None:
        """Safely remove a directory and its contents."""
        shutil.rmtree(path, ignore_errors=True)

    @staticmethod
    def copy_file(src: str, dst: str) -> None:
        """Copy a single file."""
        shutil.copy2(src, dst)
        
    @staticmethod
    def copy_tree(src: str, dst: str) -> None:
        """Copy an entire directory tree."""
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    @staticmethod
    def zip_directory(source_dir: str, zip_path: str) -> None:
        """Zip the contents of a directory."""
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for root, _, files in os.walk(source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    archive.write(file_path, os.path.relpath(file_path, source_dir))

    @staticmethod
    def extract_archive(archive_path: str, extract_to: str) -> None:
        """Extract a zip or tar archive to a directory."""
        if archive_path.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                zip_ref.extractall(extract_to)
        elif archive_path.endswith((".tar.gz", ".tgz")):
            with tarfile.open(archive_path, "r:gz") as tar_ref:
                tar_ref.extractall(extract_to)
        else:
            raise ValueError(f"Unsupported archive format: {archive_path}")

    @staticmethod
    def get_dir_size_mb(path: str) -> float:
        """Calculate the total size of a directory in Megabytes."""
        total_size = 0
        if os.path.exists(path):
            for root, _, files in os.walk(path):
                for f in files:
                    filepath = os.path.join(root, f)
                    if not os.path.islink(filepath):
                        total_size += os.path.getsize(filepath)
        return total_size / (1024 * 1024)
