"""Conservative filesystem primitives. Never unlink documents or remove folders.

macOS uses fcopyfile(COPYFILE_ALL) and renameatx_np(RENAME_EXCL).
Linux is supported for tests with renameat2(RENAME_NOREPLACE). No unsafe fallback.
"""
from contextlib import contextmanager
import ctypes
import hashlib
import os
from pathlib import Path
import stat
import sys
import unicodedata

LIBC = ctypes.CDLL(None, use_errno=True)
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


def key(name):
    return unicodedata.normalize('NFC', name).casefold()


@contextmanager
def directory(path, create=False, boundary=None):
    """Walk held directory descriptors; reject symlinks, including ancestors."""
    path = Path(path).absolute()
    fd = os.open('/', DIR_FLAGS)
    try:
        current = Path('/')
        for part in path.parts[1:]:
            current /= part
            try:
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if not create or boundary is None or current == boundary or not current.is_relative_to(boundary):
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd); fd = child
        yield fd
    finally:
        os.close(fd)


class _DarwinStatfs(ctypes.Structure):
    # SDK sys/mount.h, __DARWIN_STRUCT_STATFS64 (64-bit macOS).
    _fields_ = [('bsize',ctypes.c_uint32),('iosize',ctypes.c_int32),
                ('counts',ctypes.c_uint64*5),('fsid',ctypes.c_int32*2),
                ('owner',ctypes.c_uint32),('type',ctypes.c_uint32),
                ('flags',ctypes.c_uint32),('subtype',ctypes.c_uint32),
                ('fstype',ctypes.c_char*16),('mounted',ctypes.c_char*1024),
                ('source',ctypes.c_char*1024),('extended',ctypes.c_uint32),
                ('reserved',ctypes.c_uint32*7)]


def require_local(path):
    if sys.platform != 'darwin': return  # Linux is a development/test host.
    with directory(path) as fd:
        info = _DarwinStatfs()
        call = getattr(LIBC,'fstatfs$INODE64',LIBC.fstatfs)
        if call(fd,ctypes.byref(info)):raise OSError(ctypes.get_errno(),'Volume non vérifiable')
        if not info.flags & 0x1000 or info.fstype not in (b'apfs',b'hfs'):
            raise ValueError('Classement protégé réservé à un volume local APFS ou Mac OS étendu. Aucun original retiré.')


def identity(path):
    with directory(path) as fd:
        s = os.fstat(fd)
        return [s.st_dev, s.st_ino]


def anchors(root, parent):
    """Record every existing parent, so a stale confirmation cannot recreate it."""
    root, parent = Path(root), Path(parent)
    if not parent.is_relative_to(root):
        raise ValueError('Destination hors de la racine autorisée.')
    result = {str(root): identity(root)}
    current = root
    for part in parent.relative_to(root).parts:
        current /= part
        try: result[str(current)] = identity(current)
        except FileNotFoundError: break
    return result


def check_anchors(expected):
    for path, ident in expected.items():
        if identity(path) != ident:
            raise ValueError('Un dossier a été remplacé. Choisissez à nouveau la destination.')


def acl(fd):
    if sys.platform != 'darwin': return ''
    LIBC.acl_get_fd.restype = ctypes.c_void_p
    LIBC.acl_to_text.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    LIBC.acl_to_text.restype = ctypes.c_void_p
    LIBC.acl_free.argtypes = [ctypes.c_void_p]
    obj = LIBC.acl_get_fd(fd)
    if not obj:
        if ctypes.get_errno() == 2: return ''  # Darwin: no extended ACL (ENOENT).
        raise OSError(ctypes.get_errno(), 'Impossible de lire les autorisations du fichier')
    text = None
    try:
        text = LIBC.acl_to_text(obj, None)
        if not text: raise OSError(ctypes.get_errno(), 'Impossible de lire les autorisations du fichier')
        return ctypes.string_at(text).decode()
    finally:
        if text: LIBC.acl_free(text)
        LIBC.acl_free(obj)


def xattrs(fd):
    if sys.platform != 'darwin':
        return {k: os.getxattr(fd,k).hex() for k in sorted(os.listxattr(fd))}
    LIBC.flistxattr.restype = ctypes.c_ssize_t
    LIBC.fgetxattr.restype = ctypes.c_ssize_t
    size = LIBC.flistxattr(fd, None, 0, 0)
    if size < 0: raise OSError(ctypes.get_errno(), 'Lecture des attributs impossible')
    buf = ctypes.create_string_buffer(size)
    actual = LIBC.flistxattr(fd, buf, size, 0)
    if actual < 0: raise OSError(ctypes.get_errno(), 'Attributs modifiés pendant lecture')
    result = {}
    for key in filter(None,buf.raw[:actual].split(b'\0')):
        size = LIBC.fgetxattr(fd,key,None,0,0,0)
        if size < 0: raise OSError(ctypes.get_errno(), 'Lecture attribut impossible')
        value = ctypes.create_string_buffer(size)
        actual = LIBC.fgetxattr(fd,key,value,size,0,0)
        if actual < 0: raise OSError(ctypes.get_errno(), 'Attribut modifié pendant lecture')
        result[os.fsdecode(key)] = value.raw[:actual].hex()
    return result


def fingerprint_fd(fd):
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode): raise ValueError('Seuls les fichiers ordinaires sont acceptés.')
    h = hashlib.sha256(); os.lseek(fd, 0, os.SEEK_SET)
    while block := os.read(fd, 1024 * 1024): h.update(block)
    attrs = xattrs(fd)
    permissions = acl(fd)
    after = os.fstat(fd)
    if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError('Fichier modifié pendant sa vérification. Toutes les copies sont conservées.')
    return dict(device=after.st_dev, inode=after.st_ino, ctime=after.st_ctime_ns,
                size=after.st_size, sha256=h.hexdigest(), mode=stat.S_IMODE(after.st_mode),
                uid=after.st_uid, gid=after.st_gid, mtime=after.st_mtime_ns,
                flags=getattr(after, 'st_flags', 0), xattrs=attrs, acl=permissions)


def fingerprint(path):
    path = Path(path)
    with directory(path.parent) as parent:
        fd = os.open(path.name, FILE_FLAGS, dir_fd=parent)
        try: return fingerprint_fd(fd)
        finally: os.close(fd)


def content(fp):
    return {k: v for k, v in fp.items() if k not in ('device', 'inode', 'ctime')}


def exclusive_rename(source_fd, source, target_fd, target):
    if sys.platform == 'darwin':
        result = LIBC.renameatx_np(source_fd, os.fsencode(source), target_fd, os.fsencode(target), 4)
    elif sys.platform.startswith('linux') and hasattr(LIBC, 'renameat2'):
        result = LIBC.renameat2(source_fd, os.fsencode(source), target_fd, os.fsencode(target), 1)
    else:
        raise ValueError('Ce système ne permet pas le déplacement protégé. Aucun original retiré.')
    if result: raise OSError(ctypes.get_errno(), 'Déplacement exclusif refusé (destination occupée ou volume différent).')
    os.fsync(target_fd); os.fsync(source_fd)


def require_free(parent, name):
    if any(key(n) == key(name) for n in os.listdir(parent)):
        raise ValueError('La destination est déjà occupée. Aucun fichier ne sera remplacé.')


def copy_verified(source, target, boundary, expected=None):
    """Independent copy, metadata included; private staging retained on any failure.

    Caller journals the unique target *before* this call. It is never reused.
    """
    source, target = Path(source), Path(target)
    with directory(source.parent) as sp, directory(target.parent, True, Path(boundary)) as tp:
        require_free(tp, target.name)
        sf = os.open(source.name, FILE_FLAGS, dir_fd=sp)
        df = None
        try:
            before = fingerprint_fd(sf)
            if expected is not None and before != expected:
                raise ValueError('Le fichier a changé depuis la confirmation. Recommencez après vérification.')
            df = os.open(target.name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=tp)
            if sys.platform == 'darwin':
                os.lseek(sf, 0, os.SEEK_SET)
                if LIBC.fcopyfile(sf, df, None, 15):
                    raise OSError(ctypes.get_errno(), 'Copie des données et métadonnées impossible')
            else:
                os.lseek(sf, 0, os.SEEK_SET)
                while block := os.read(sf, 1024 * 1024):
                    view = memoryview(block)
                    while view: view = view[os.write(df, view):]
                os.fchmod(df, before['mode'])
                for k, v in before['xattrs'].items(): os.setxattr(df, k, bytes.fromhex(v))
                os.utime(df, ns=(os.fstat(sf).st_atime_ns, before['mtime']))
            os.fsync(df); os.fsync(tp)
            after, copied = fingerprint_fd(sf), fingerprint_fd(df)
            if before != after or content(before) != content(copied):
                raise ValueError('La vérification de la copie a échoué. Original et copie conservés.')
            # A source renamed/replaced by Finder is not the object we confirmed.
            named = os.stat(source.name, dir_fd=sp, follow_symlinks=False)
            if (named.st_dev, named.st_ino) != (before['device'], before['inode']):
                raise ValueError('Le fichier source a été déplacé pendant la copie.')
            return copied
        finally:
            if df is not None: os.close(df)
            os.close(sf)


def publish(source, target, root, expected=None, temporary=None):
    """Verify a separate temporary copy before its exclusive publication."""
    import uuid
    target = Path(target)
    temporary = Path(temporary) if temporary else target.parent / ('.mailord-' + uuid.uuid4().hex + '.tmp')
    copied = copy_verified(source, temporary, root, expected)
    with directory(target.parent) as parent:
        require_free(parent, target.name)
        exclusive_rename(parent, temporary.name, parent, target.name)
    final = fingerprint(target)
    if (final['device'], final['inode']) != (copied['device'], copied['inode']) or content(final) != content(copied):
        raise ValueError('Destination modifiée après publication. Les copies sont conservées.')
    return final


def retire(source, retained, expected):
    """Move the actual directory entry into recovery, never unlink it.

    A swap after the precheck is captured, not destroyed. The independent snapshot
    still protects the confirmed bytes even if an editor keeps this inode open.
    """
    source, retained = Path(source), Path(retained)
    with directory(source.parent) as sp, directory(retained.parent) as rp:
        if os.fstat(sp).st_dev != os.fstat(rp).st_dev:
            raise ValueError('Déplacement entre volumes refusé : l’original reste en place.')
        if fingerprint(source) != expected:
            raise ValueError('Source modifiée : original conservé à son emplacement.')
        exclusive_rename(sp, source.name, rp, retained.name)
        captured = fingerprint(retained)
        if (captured['device'], captured['inode']) != (expected['device'], expected['inode']) or content(captured) != content(expected):
            raise ValueError('Modification concurrente : fichier capturé conservé dans la récupération.')
    return captured
