# Shared contract fixtures (WS-0)

These five payloads exist twice — `bierre/tests/fixtures/` and `bierre-ca/tests/fixtures/` — and
the two copies are **byte-identical**. The back-end asserts that what it serves matches them; the
front-end asserts that what it parses matches them. Neither side can quietly change the wire
contract, because changing it means changing a file the other side also tests against.

| File | Route |
| --- | --- |
| `login.json` | `POST /accounts/api/auth/login` response |
| `me.json` | `GET /accounts/api/auth/me` response, and `login.json`'s `user` object |
| `profiles_list.json` | `GET /accounts/api/profiles` response |
| `profile_get.json` | `GET /accounts/api/profiles/{id}` response |
| `error.json` | The error body shape used by every route in both services |

The authority for the shapes is `bierre-ca/docs/openapi-slice1.yaml`. These files are examples of
it, not a second source of truth.

## Things the fixtures deliberately demonstrate

- **`email_verified` is `false`.** Slice 1 sends no mail, so a real account stays unverified.
  Anything that gates on a verified email is a bug in this slice.
- **`profiles_list.json` contains `antimicrobial-review-2`.** The collision suffix is a normal
  part of the id space, not an error state. Two profiles may share a `label`; they never share a
  slug.
- **`profile_get.json` ends its `buckets` list with the `fallback` bucket.** Bucket matching is
  first-match-wins, so a fallback anywhere but last swallows everything after it.
- **`access_token` in `login.json` decodes but does not verify.** The claims are real enough to
  assert against (`iss`, `aud`, `typ: access`, 15-minute `exp`); the signature is the literal
  string `fixture-signature-is-not-verifiable`. Never feed it to a code path that is supposed to
  accept it.

## Changing a fixture

1. Update `bierre-ca/docs/openapi-slice1.yaml` first, if the shape changed.
2. Edit the file in one repo, copy it to the other verbatim, and regenerate the manifest in both:

   ```bash
   cd tests/fixtures && shasum -a 256 *.json > MANIFEST.sha256
   ```

3. Run both test suites. `MANIFEST.sha256` is itself byte-identical across the repos, so a fixture
   edited in only one of them fails there immediately.
