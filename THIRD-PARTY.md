# Third-party components

DeadBolt's own source is Apache-2.0. Dependency components retain their original
licenses. The image includes `THIRD-PARTY-NOTICES.txt`, the inventory for the
locked engine dependency closure. This inventory includes components conditional
on other supported targets and is broader than the exact linked set on one
platform. Base-image components also retain their own licenses.

The Docker build copies `third-party/` from the checksum-pinned engine source
archive into `/opt/deadbolt/third-party/` in the runtime image. That directory
includes the unmodified source and original MPL-2.0 license for `option-ext`
0.2.0 and the Rust 1.85.0 runtime license and copyright notices. The option-ext
source is also available in the [exact upstream crate](https://crates.io/crates/option-ext/0.2.0).
It is a source distribution for recipients, not a patched Cargo dependency.
See [Mozilla's distribution FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/).

To regenerate the engine dependency inventory, use Python 3.11+ in the pinned
engine source checkout after resolving its locked Cargo dependencies:

```sh
python3 dist/collect_licenses.py THIRD-PARTY-NOTICES.txt
```

If a dependency, toolchain or base image changes, review its licenses and notices
and update any required source distribution before publishing. Third-party
license texts do not change DeadBolt's own license.
