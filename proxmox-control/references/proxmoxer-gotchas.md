# proxmoxer gotchas (verified against proxmoxer==2.3.0 on Python 3.11)

## Token auth kwarg names
proxmoxer's `ProxmoxAPI(..., backend='https')` accepts:
- `user="root@pam"`
- `token_name="agent"`   # the part AFTER '!' in the token_id
- `token_value="<secret>"`

It does NOT accept `token_secret`. Passing `token_secret=` raises:
`TypeError: Backend.__init__() got an unexpected keyword argument 'token_secret'`.

Resolution: split the token_id on '!':
```python
token_id = "root@pam!agent"
token_name = token_id.split("!", 1)[1]   # -> "agent"
```

## Connection timing: eager vs lazy
Verified by constructing clients against a non-routable IP (192.168.8.250):

- **password auth**: connects AT CONSTRUCTION. `ProxmoxAPI(..., password=...)` immediately POSTs `/api2/json/access/ticket` to fetch a ticket. If the host is unreachable it raises `requests.exceptions.ConnectionError` at the `ProxmoxAPI(...)` call site — NOT at first `.get()`.
- **token auth**: LAZY. Construction succeeds with no network. The first real API call (e.g. `.nodes.get()`) is what hits the network.

Implication for `get_all()`: a dict comprehension `{n: build_client(n,c) ...}` will ABORT on the first unreachable password host. Wrap each build in try/except and store the Exception in the dict so the batch survives partial failure:
```python
out = {}
for name, cfg in reg["hosts"].items():
    try:
        out[name] = build_client(name, cfg)
    except Exception as e:
        out[name] = e
```

## Exception classes for error handling (verify before documenting!)
proxmoxer 2.x exposes ONLY these at the top level — there is NO `ProxmoxAPIError` and NO `ProxmoxWebAPIError` class (both raise `ImportError` if imported; commonly cited in old snippets):

```python
from proxmoxer import ResourceException, AuthenticationError
# ResourceException -> API/HTTP failures (4xx/5xx from the PVE API)
# AuthenticationError -> bad/missing creds or token
```

Verify inside the skill venv before trusting a copied snippet:
```bash
.venv/bin/python -c "import proxmoxer; print([n for n in dir(proxmoxer) if 'rror' in n])"
# -> ['AuthenticationError', 'ResourceException']
```

## Backend dependency
proxmoxer's default `https` backend imports `requests`. Without it you get:
`Chosen backend requires 'requests' module`. Install `requests` alongside `proxmoxer`.

## Auth troubleshooting (summary)
- 401 realm: `user@pam` != `user@pve` (different auth domains). Try the other.
- 401 token "exists but fails": often a missing role/ACL. Fix on the PVE side.
- Token secret REGENERATES if you edit the token in the PVE UI — re-copy it.
- SSL on LAN: `verify_ssl=False`. Production: install the PVE CA and set True.
