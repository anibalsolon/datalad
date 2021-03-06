# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helper for RIA stores

"""


class UnknownLayoutVersion(Exception):
    pass


# TODO: Make versions a tuple of (label, description)?
# Object tree versions we introduced so far. This is about the layout within a
# dataset in a RIA store
known_versions_objt = ['1', '2']
# Dataset tree versions we introduced so far. This is about the layout of
# datasets in a RIA store
known_versions_dst = ['1']


# TODO: This is wrong and should consider both versions (store+dataset)
def get_layout_locations(version, base_path, dsid):
    """Return dataset-related path in a RIA store

    Parameters
    ----------
    version : int
      Layout version of the store.
    base_path : Path
      Base path of the store.
    dsid : str
      Dataset ID

    Returns
    -------
    Path, Path, Path
      The location of the bare dataset repository in the store,
      the directory with archive files for the dataset, and the
      annex object directory are return in that order.
    """
    if version == 1:
        dsgit_dir = base_path / dsid[:3] / dsid[3:]
        archive_dir = dsgit_dir / 'archives'
        dsobj_dir = dsgit_dir / 'annex' / 'objects'
        return dsgit_dir, archive_dir, dsobj_dir
    else:
        raise ValueError("Unknown layout version: {}. Supported: {}"
                         "".format(version, known_versions_dst))


def verify_ria_url(url, cfg):
    """Verify and decode ria url

    Expects a ria-URL pointing to a RIA store, applies rewrites and tries to
    decode potential host and base path for the store from it. Additionally
    raises if `url` is considered invalid.

    ria+ssh://somehost:/path/to/store
    ria+file:///path/to/store

    Parameters
    ----------
    url : str
      URL to verify an decode.
    cfg : dict-like
      Configuration settings for rewrite_url()

    Raises
    ------
    ValueError

    Returns
    -------
    tuple
      (host, base-path, rewritten url)
    """
    from datalad.config import rewrite_url
    from datalad.support.network import URL

    if not url:
        raise ValueError("Got no URL")

    url = rewrite_url(cfg, url)
    url_ri = URL(url)
    if not url_ri.scheme.startswith('ria+'):
        raise ValueError("Missing ria+ prefix in final URL: %s" % url)
    if url_ri.fragment:
        raise ValueError(
            "Unexpected fragment in RIA-store URL: %s" % url_ri.fragment)
    protocol = url_ri.scheme[4:]
    if protocol not in ['ssh', 'file']:
        raise ValueError("Unsupported protocol: %s. Supported: ssh, file" %
                         protocol)

    return url_ri.hostname if protocol == 'ssh' else None, url_ri.path, url


def create_store(io, base_path, version):
    """Helper to create a RIA store

    Note, that this is meant as an internal helper and part of intermediate
    RF'ing. Ultimately should lead to dedicated command or option for
    create-sibling-ria.

    Parameters
    ----------
    io: SSHRemoteIO or LocalIO
      Respective execution instance.
      Note: To be replaced by proper command abstraction
    base_path: Path
      root path of the store
    version: str
      layout version of the store (dataset tree)
    """

    # At store level the only version we know as of now is 1.
    if version not in known_versions_dst:
        raise UnknownLayoutVersion("RIA store layout version unknown: {}."
                                   "Supported versions: {}"
                                   .format(version, known_versions_dst))

    error_logs = base_path / 'error_logs'
    version_file = base_path / 'ria-layout-version'
    # TODO: Check base path for being empty?
    #       Requires proper IO (command abstraction class).
    #       But: Likely unnecessary. For now, check for version conflict only.
    if io.exists(version_file):
        existing_version = io.read_file(version_file).split('|')[0].strip()
        if existing_version != version.split('|')[0]:
            # We have an already existing location with a conflicting version on
            # record.
            # Note, that a config flag after pipe symbol is fine.
            raise ValueError("Conflicting version found at target: {}"
                             .format(existing_version))
        else:
            # already exists, recorded version fits - nothing to do
            return

    # Note, that the following does create the base-path dir as well, since
    # mkdir has parents=True:
    io.mkdir(error_logs)
    io.write_file(version_file, version)


def create_ds_in_store(io, base_path, dsid, obj_version, store_version):
    """Helper to create a dataset in a RIA store

    Note, that this is meant as an internal helper and part of intermediate
    RF'ing. Ultimately should lead to a version option for create-sibling-ria
    in conjunction with a store creation command/option.

    Parameters
    ----------
    io: SSHRemoteIO or LocalIO
      Respective execution instance.
      Note: To be replaced by proper command abstraction
    base_path: Path
      root path of the store
    dsid: str
      dataset id
    store_version: str
      layout version of the store (dataset tree)
    obj_version: str
      layout version of the dataset itself (object tree)
    """

    # TODO: Note for RF'ing, that this is about setting up a valid target
    #       for the special remote not a replacement for create-sibling-ria.
    #       There's currently no git (bare) repo created.

    try:
        # TODO: This is currently store layout version!
        #       Too entangled by current get_layout_locations.
        dsgit_dir, archive_dir, dsobj_dir = \
            get_layout_locations(int(store_version), base_path, dsid)
    except ValueError as e:
        raise UnknownLayoutVersion(str(e))

    if obj_version not in known_versions_objt:
        raise UnknownLayoutVersion("Dataset layout version unknown: {}. "
                                   "Supported: {}"
                                   .format(obj_version, known_versions_objt))

    version_file = dsgit_dir / 'ria-layout-version'

    if version_file.exists():
        existing_version = version_file.read_text().split('|')[0].strip()
        if existing_version != obj_version.split('|')[0]:
            # We have an already existing location with a conflicting version on
            # record.
            # Note, that a config flag after pipe symbol is fine.
            raise ValueError("Conflicting dataset layout version found at "
                             "target: {}".format(existing_version))

    io.mkdir(archive_dir)
    io.mkdir(dsobj_dir)
    io.write_file(version_file, obj_version)
