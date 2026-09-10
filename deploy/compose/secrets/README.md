# Runtime secret files

Create `recordlane-master-key.txt`, `recordlane-scim-token.txt`, and
`recordlane-metrics-token.txt` here before
starting the production Compose profile. Use independently generated random
values of at least 32 bytes, set file mode `0600`, and do not commit them.

The repository ignores `*.txt` in this directory. The `.example` files describe
the expected shape but are not usable credentials.
