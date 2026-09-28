# Local common-password list

`common-passwords.txt.gz` is an unmodified copy from Django tag **5.2**:
https://github.com/django/django/blob/5.2/django/contrib/auth/common-passwords.txt.gz

SHA-256: `3c1baed62596de36860824eb3f436d5932d37ca8b06e59df78f5a44ec175afe4`

The snapshot contains 19,640 entries. Django distributes it under its BSD
three-clause license, reproduced in `DJANGO-LICENSE.txt`. Django attributes
the source list to Royce Williams; see its
[CommonPasswordValidator](https://github.com/django/django/blob/5.2/django/contrib/auth/password_validation.py).

Neodermo screens a lowercase copy of a proposed password against this local
snapshot. It hashes the original unchanged password. No network lookup or Django
runtime dependency is involved. This finite list is not an exhaustive breach
database. Update deliberately by reviewing the source/license, replacing the
snapshot, recording its version/checksum, and running the password tests.
