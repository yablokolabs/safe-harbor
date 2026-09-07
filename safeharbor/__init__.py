"""Safe Harbor — reproducible deployment, recovery, validation and migration
of persistent local AI agent environments.

Safe Harbor is a Yabloko Labs open-source project. It makes the execution
environment replaceable while preserving verifiable agent continuity.
"""

__version__ = "0.1.0"

#: The Gen1 reference architecture. Bump this whenever the persistent-state
#: layout or manifest schema changes incompatibly.
GEN1_GENERATION = 1

#: Schema version of backup manifests produced by this release.
BACKUP_SCHEMA_VERSION = 1