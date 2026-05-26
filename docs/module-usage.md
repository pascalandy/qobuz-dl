# Module usage

`qobuz-dl` can be used from Python by importing `QobuzDL` from `qobuz_dl.core`.

```python
import logging
from qobuz_dl.core import QobuzDL

logging.basicConfig(level=logging.INFO)

email = "your@email.com"
password = "your_password"

qobuz = QobuzDL()
qobuz.get_tokens()  # get 'app_id' and 'secrets' attrs
qobuz.initialize_client(email, password, qobuz.app_id, qobuz.secrets)

qobuz.handle_url("https://play.qobuz.com/album/va4j3hdlwaubc")
```

Attributes, methods, and parameters are named to describe their purpose.
