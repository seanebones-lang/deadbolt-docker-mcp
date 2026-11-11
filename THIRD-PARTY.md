# Third-party components

DeadBolt's own source is Apache-2.0. Dependency components retain their original
licenses. The image includes `THIRD-PARTY-NOTICES.txt`, the inventory for the
locked engine dependency closure. This inventory includes components conditional
on other supported targets and is broader than the exact linked set on one
platform. Base-image components also retain their own licenses.

The 2.0.2 inventory is copied byte-for-byte from the official
`deadbolt-2.0.2-x86_64-unknown-linux-gnu.zip` release archive (SHA-256
`c2e1e50fba85a5014f2c2ac9eafeceadc8c06ec2c24aef7f8b121ad836639d9f`).
Its Cargo.lock matches the checksum-pinned engine source in `SOURCE.json`.
The inventory's SHA-256 is
`f7e7e8a2527f755b6b154d35e931e7cfff2c2f11de7f621a9ca431414c1d0fa7`.

The Docker build copies `third-party/` from the checksum-pinned engine source
archive into `/opt/deadbolt/third-party/` in the runtime image. That directory
includes the unmodified source and original MPL-2.0 license for `option-ext`
0.2.0 and the Rust 1.89.0 runtime license and copyright notices. The option-ext
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
