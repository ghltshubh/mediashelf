# Security

MediaShelf is maintained by one person in his spare time. That shapes what this
document can honestly promise, so the promises here are small and real.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private reporting on this repository: **Security → Report a vulnerability**.
It opens a private thread visible only to you and me. If that is unavailable to you, email
**shubhankargahlot@gmail.com** with "MediaShelf security" in the subject.

What helps, in rough order of usefulness: what an attacker gains, the steps to reproduce it,
the version (`Settings → About`), and whether the problem is in the server, the browser
extension, or the desktop spike.

What to expect: an acknowledgement within **7 days**, and an honest assessment of whether and
when I can fix it. If a fix will be slow, I will say so rather than go quiet. Credit in the
release notes unless you would rather not have it.

## Supported versions

The **latest release** only. There are no backports and no long-term support branches. The
project is young enough that upgrading is the fix.

## Where the risk actually is

Worth knowing before you go looking, and worth taking seriously if you run it:

- **Provider tokens.** A server that you have connected to Spotify, YouTube, Apple Music or
  Trakt holds OAuth refresh tokens for those accounts. They are encrypted at rest with NaCl
  SecretBox under a per-install key in the data directory, and are never logged, but the
  running process can use them. Anyone who can reach that process, or read both the database
  and the key file, has your accounts.
- **The browser extension.** It holds host permissions on ten streaming domains where you are
  signed in, plus an optional all-URLs permission for services outside the shipped list, which
  is granted only when you ask for it. It reads the page and posts titles to the MediaShelf
  address you configured. Narrowing those permissions is [known
  debt](ROADMAP.md#known-debt).
- **No authentication of its own.** MediaShelf assumes it sits on a network you control. It has
  no login, no user accounts and no authorisation model. Do not expose it to the internet
  without putting something in front of it.
- **Your own API keys.** Nothing ships with embedded keys, and none of your keys leave your
  server except to the provider they belong to.

## Out of scope

- Reports that MediaShelf has no login. That is documented above, not a finding.
- Automated scanner output with no demonstrated impact.
- Anything requiring physical access to a machine that already holds the secret key.
- The third-party services MediaShelf links out to. Report those to their owners.
