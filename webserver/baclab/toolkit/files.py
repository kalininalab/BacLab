"""File helpers shared by the tools: running commands, zipping, copying results, naming uploads."""
import glob
import os
import re
import shutil
import subprocess
import zipfile


class CommandFailed(subprocess.CalledProcessError):
    """A tool's script exited with an error. Keeps stdout/stderr (the job's error log reads them) and
    puts the tail of stderr into str(), which is what the admin e-mail shows."""

    def __str__(self):
        stderr = (self.stderr or '').strip()
        tail = '\n'.join(stderr.splitlines()[-40:])
        return f"Command failed with return code {self.returncode}\nError:\n{tail}"


def run_command(command, cwd):
    """Run a script in cwd; raises CommandFailed (with its output) on a non-zero exit."""
    proc = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise CommandFailed(proc.returncode, command, output=proc.stdout, stderr=proc.stderr)
    return proc.stdout, proc.stderr

def zip_folder(source_dir, zip_path, exclude_extensions=None):
    """Zip the contents of a directory."""
    if exclude_extensions is None:
        exclude_extensions = []
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for root, _, files in os.walk(source_dir):
            for file in files:
                if any(file.endswith(ext) for ext in exclude_extensions):
                    continue
                file_path = os.path.join(root, file)
                archive.write(file_path, os.path.relpath(file_path, source_dir))

class ZipRejected(ValueError):
    """The uploaded zip archive is not acceptable; the message is shown to the user."""


MAX_ZIP_BYTES = 5 * 1024 ** 3   # unpacked size limit for an uploaded archive


def zip_members(archive, extensions, min_files, max_files):
    """The files of an uploaded zip to use, after checking that it is what the tool expects: a readable,
    unencrypted archive of min_files..max_files files, all with one of the extensions (macOS leftovers like
    __MACOSX/ and ._* files are ignored), no unsafe paths or duplicate names, and a sane unpacked size."""
    try:
        zf = zipfile.ZipFile(archive)
    except zipfile.BadZipFile:
        raise ZipRejected("The uploaded file is not a valid zip archive.")
    members = [i for i in zf.infolist() if not i.is_dir() and not i.filename.startswith('__MACOSX/')
               and not os.path.basename(i.filename).startswith(('._', '.DS_Store'))]
    if len(members) > max_files:
        raise ZipRejected(f"The zip archive contains {len(members)} files, at most {max_files} are allowed.")
    if len(members) < min_files:
        raise ZipRejected(f"The zip archive must contain at least {min_files} files.")
    seen = set()
    for member in members:
        name = member.filename
        if name.startswith('/') or '..' in name.replace('\\', '/').split('/'):
            raise ZipRejected(f"The zip archive contains an unsafe path: \"{name}\".")
        if member.flag_bits & 0x1:
            raise ZipRejected("Password-protected zip archives are not supported.")
        if not name.lower().endswith(tuple(extensions)):
            raise ZipRejected(f"\"{name}\" in the zip archive has an unsupported extension. Allowed extensions: {', '.join(extensions)}.")
        flat = sanitize_filename(os.path.basename(name))
        if flat in seen:
            raise ZipRejected(f"The zip archive contains the file name \"{os.path.basename(name)}\" more than once.")
        seen.add(flat)
    if sum(m.file_size for m in members) > MAX_ZIP_BYTES:
        raise ZipRejected(f"The zip archive is larger than {MAX_ZIP_BYTES // 1024 ** 3} GB when unpacked.")
    return zf, members


def extract_zip(archive_path, input_dir, extensions, min_files, max_files):
    """Unpack a zip (checked as above) flat into input_dir, then delete it. The declared sizes in a zip can
    lie, so the real unpacked size is counted while writing."""
    zf, members = zip_members(archive_path, extensions, min_files, max_files)
    written = 0
    with zf:
        for member in members:
            with zf.open(member) as source, open(os.path.join(input_dir, sanitize_filename(os.path.basename(member.filename))), 'wb') as target:
                while chunk := source.read(1024 * 1024):
                    written += len(chunk)
                    if written > MAX_ZIP_BYTES:
                        raise ZipRejected(f"The zip archive is larger than {MAX_ZIP_BYTES // 1024 ** 3} GB when unpacked.")
                    target.write(chunk)
    os.remove(archive_path)


def sanitize_filename(name):
    """Replace characters that can break a shell-invoked tool's own internal file handling (spaces,
    parentheses, quotes, etc.) with underscores. Confirmed necessary: a browser-appended "(1)" in an
    uploaded filename (from downloading the same file twice) made CheckM2's internal gene-calling
    step fail outright with a missing-file error - it builds intermediate filenames by suffixing the
    input's own name, and the literal parentheses broke that."""
    return re.sub(r'[^A-Za-z0-9._-]', '_', name)

def saved_name(request, field):
    """The file name an upload of this form field was saved under in the job's input folder (handle_job
    sanitizes it), or None if nothing was uploaded."""
    names = getattr(request, 'saved_files', {}).get(field)
    return names[0] if names else None


def rename_uploaded_input(input_path, saved_filename, new_basename):
    """Rename an already-saved upload (see saved_name) to a fixed, predictable basename while
    preserving its extension, so shell scripts can glob for it deterministically."""
    if not saved_filename:
        return None
    parts = saved_filename.split('.', 1)
    ext = f".{parts[1]}" if len(parts) > 1 else ""
    src = os.path.join(input_path, saved_filename)
    dst = os.path.join(input_path, f"{new_basename}{ext}")
    if os.path.exists(src) and src != dst:
        os.rename(src, dst)
    return dst

def matching_file_in_dir(dir, *patterns):
    for pattern in patterns:
        hits = glob.glob(os.path.join(dir, pattern))
        if hits:
            return sorted(hits)[0]
    return None

def copy_selected_files(output_dir, downloads_dir, filenames):
    """Copy just the given top-level filenames from output_dir into downloads_dir, for tools whose
    output is one working directory full of intermediates but only a couple of files are useful."""
    os.makedirs(downloads_dir, exist_ok=True)
    for filename in filenames:
        src = os.path.join(output_dir, filename)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(downloads_dir, filename))

def copy_dirs(output_dir, downloads_dir, dirnames):
    """Copy whole sub-directories of output_dir (given relative to it) into downloads_dir, keeping
    their relative paths."""
    for dirname in dirnames:
        src = os.path.join(output_dir, dirname)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(downloads_dir, dirname), dirs_exist_ok=True)

def copy_output_to_downloads(output_dir, downloads_dir):
    """Shared post-processing copy step for tools with no special result curation."""
    try:
        shutil.copytree(output_dir, downloads_dir, dirs_exist_ok=True)
    except TypeError:
        os.makedirs(downloads_dir, exist_ok=True)
        for root, dirs, files in os.walk(output_dir):
            rel = os.path.relpath(root, output_dir)
            target_root = downloads_dir if rel == '.' else os.path.join(downloads_dir, rel)
            os.makedirs(target_root, exist_ok=True)
            for f in files:
                shutil.copy2(os.path.join(root, f), os.path.join(target_root, f))

def prune_paths(directory, patterns):
    """Delete what matches the given names / sub-folders / glob patterns (relative to directory): working data that is not a result."""
    for pattern in patterns:
        for path in glob.glob(os.path.join(directory, pattern), recursive=True):
            if os.path.islink(path) or os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
            elif os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)


def copy_input_to_downloads(output_dir, downloads_dir):
    """Copy the job's original input files into downloads_dir/input. Called unconditionally for
    every job type after its post-processing step, so results always include what the user
    submitted regardless of how that step curated the rest of downloads_dir."""
    input_dir = os.path.join(output_dir, 'input')
    if not os.path.isdir(input_dir):
        return
    dest = os.path.join(downloads_dir, 'input')
    try:
        shutil.copytree(input_dir, dest, dirs_exist_ok=True)
    except TypeError:
        os.makedirs(dest, exist_ok=True)
        for root, dirs, files in os.walk(input_dir):
            rel = os.path.relpath(root, input_dir)
            target_root = dest if rel == '.' else os.path.join(dest, rel)
            os.makedirs(target_root, exist_ok=True)
            for f in files:
                shutil.copy2(os.path.join(root, f), os.path.join(target_root, f))


def copy_outputs(output_dir, downloads_dir, patterns):
    """Copy what matches the given names / sub-folders / glob patterns (relative to output_dir) into
    downloads_dir, keeping their relative paths. Missing names are skipped."""
    os.makedirs(downloads_dir, exist_ok=True)
    for pattern in patterns:
        for src in sorted(glob.glob(os.path.join(output_dir, pattern))):
            dst = os.path.join(downloads_dir, os.path.relpath(src, output_dir))
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)


def rename_uploads(*fields):
    """prepare_inputs for a Tool: give the uploads in these form fields fixed names (field name + original extension)."""
    def prepare_inputs(request, input_dir):
        for field in fields:
            rename_uploaded_input(input_dir, saved_name(request, field), field)
    return prepare_inputs


def unpack_archive(form):
    """prepare_inputs for a Tool whose genome_form(allow_zip=True) accepts a zip: unpack an uploaded archive into the input folder."""
    def prepare_inputs(request, input_dir):
        archive = saved_name(request, 'archive')
        if archive:
            extract_zip(os.path.join(input_dir, archive), input_dir, form.ALLOWED_EXTENSIONS, form.MIN_GENOMES, form.MAX_GENOMES)
    return prepare_inputs
