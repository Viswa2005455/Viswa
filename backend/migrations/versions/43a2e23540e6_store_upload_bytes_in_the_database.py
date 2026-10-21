"""store upload bytes in the database

Earlier versions kept each upload's original bytes on disk at storage/uploads/<id>.bin. They now
live in `upload_blobs`, so a hosted copy needs no persistent disk. Existing files are copied in;
the server's hourly housekeeping deletes each disk copy once its bytes are in the database.

Revision ID: 43a2e23540e6
Revises: 4517570a0e63
Create Date: 2026-10-21 12:58:40.604566

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '43a2e23540e6'
down_revision: Union[str, Sequence[str], None] = '4517570a0e63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

uploads = sa.table("uploads", sa.column("id", sa.Uuid()))
blobs = sa.table("upload_blobs", sa.column("upload_id", sa.Uuid()), sa.column("data", sa.LargeBinary()))


def _upload_dir():
    from app.config import get_settings
    return get_settings().upload_dir


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('upload_blobs',
    sa.Column('upload_id', sa.Uuid(), nullable=False),
    sa.Column('data', sa.LargeBinary(), nullable=False),
    sa.ForeignKeyConstraint(['upload_id'], ['uploads.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('upload_id')
    )
    conn = op.get_bind()
    folder = _upload_dir()
    for (upload_id,) in conn.execute(sa.select(uploads.c.id)).all():
        path = folder / f"{upload_id.hex}.bin"
        if path.is_file():
            conn.execute(blobs.insert().values(upload_id=upload_id, data=path.read_bytes()))


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    rows = conn.execute(sa.select(blobs.c.upload_id, blobs.c.data)).all()
    if rows:
        folder = _upload_dir()
        folder.mkdir(parents=True, exist_ok=True)
        for upload_id, data in rows:
            (folder / f"{upload_id.hex}.bin").write_bytes(data)
    op.drop_table('upload_blobs')
