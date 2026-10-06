# Approval packet: in-repo whereToken formula v0.7.7

Status: `APPROVAL_REQUIRED_FUNCTIONAL`. Not applied. Not committed to whereToken.

When this packet was written, public main and the v0.7.7 tree were `6948f7522a0a98d4f7d2619583e1b717b9363162`. The annotated tag object is `61850b5c1ab872d5b94972df6b7248648e7d1666`. The tag was not moved.

Stabilization on 2026-10-06 proceeded without this change. Public main is `cd3213d9d831207766295ed7515c7d8103a455d2`, and `Formula/wheretoken.rb` on that commit is still the v0.7.6 pin. The owner has not approved the bump. v0.7.6 remains a frozen confounder for the whole traffic window.

## Exact diff

`Formula/wheretoken.rb` only. No other line in that file changes. Homebrew reads the version from the tag URL, and the formula already passes that version to `-X main.version=`.

```diff
-  url "https://github.com/rainhuang0220/whereToken/archive/refs/tags/v0.7.6.tar.gz"
-  sha256 "384780534bf6051ca546519ac74182d6f6bfb6331677c04299030a18399417bf"
+  url "https://github.com/rainhuang0220/whereToken/archive/refs/tags/v0.7.7.tar.gz"
+  sha256 "45c441683f15180330ad19b3a53f3708e9c763a3bcdcb7589e27cef3317e54e5"
```

## Verified SHA256

URL: `https://github.com/rainhuang0220/whereToken/archive/refs/tags/v0.7.7.tar.gz`

On 2026-10-05 two independent downloads hashed the same bytes:

- `curl -fsSL` piped to `shasum -a 256`
- Python `urllib` streaming SHA-256, HTTP 200, `content-type: application/x-gzip`, 5485748 bytes

Both produced `45c441683f15180330ad19b3a53f3708e9c763a3bcdcb7589e27cef3317e54e5`.

The current v0.7.6 pin remains `384780534bf6051ca546519ac74182d6f6bfb6331677c04299030a18399417bf`.

## Effect

Direct users of this in-repo formula would compile the v0.7.7 tag with `go build ./cmd/wheretoken` instead of the v0.7.6 tag. It would still be a source build of the CLI, with the man page and shell completions. It would not become the external tap's release binary.

Users of `brew tap rainhuang0220/wheretoken` are on a different repository. This diff does not change that tap. That tap already points at v0.7.7 platform archives.

`TestHomebrewFormulaTracksLatestRelease` allows the formula URL to name either of the two newest `CHANGELOG.md` versions. v0.7.6 is inside that allowance today. v0.7.7 would still pass. The test does not check the sha256.

## Rollback

Restore the two v0.7.6 lines. No tag move. No release.

## Not done

The file was not edited. `brew install` was not run. This packet is not the growth treatment and it is not a baseline gate. It stayed unapplied through the 2026-10-06 stabilization. While it stays unapplied, the v0.7.6 formula URL is a frozen confounder for experiment 2.
