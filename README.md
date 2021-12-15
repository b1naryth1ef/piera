## This repository is no longer maintained, please see [https://github.com/clearbank/piera/](https://github.com/clearbank/piera/) for an updated fork.

# Piera
Piera is a lightweight, pure-Python [Hiera](http://docs.puppetlabs.com/hiera/) parser. It was built to help bridge the gap between Puppet/Hiera and Python system scripts. Piera is currently not feature complete, lacking some less-used interoplation and loading features (feel free to contribute!)

## Why?
Piera was built at [Braintree](http://github.com/braintree) to help us bridge a gap of emerging Python system scripts, and a historical storage of Puppet/Hiera data.

## Install It

### PyPi
`pip install piera`

### Manual
```bash
git clone git@github.com:b1naryth1ef/piera.git
cd piera
python setup.py install
```

## Usage
```python
import piera

h = piera.Hiera("my_hiera.yaml")

# You can use piera to simply interact with your structured Hiera data

# key: 'value'
assert h.get("key") == "value"

# key_alias: '%{alias('key')}'
assert h.get("key_alias") == "value"

# key_hiera: 'OHAI %{hiera('key_alias')}'
assert h.get("key_hiera") == "OHAI value"

# Give piera context
assert h.get("my_context_based_key", name='test01', environment='qa') == "context is great!"
```

### Requirements

* Python 2.7+
