# Piera
Piera is a lightweight, pure-Python [Hiera](http://docs.puppetlabs.com/hiera/) parser. It was built to help bridge the gap between Puppet/Hiera and Python system scripts. Piera is currently not feature complete, lacking some less-used interoplation and loading features (feel free to contribute!)

## Why?
Piera was built at [Braintree](github.com/braintree) to help us bridge a gap of emerging Python system scripts, and a historical storage of Puppet/Hiera data.

## Usage
```python
import piera

h = piera.Hiera("my_hiera.yaml")

# key: 'value'
assert h.get("key") == "value"

# key_alias: '%{alias('key')}'
assert h.get("key_alias") == "value"

# key_hiera: 'OHAI %{hiera('key_alias')}'
assert h.get("key_hiera") == "OHAI value"
```
