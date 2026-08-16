# Architecture

`public web session -> signed state + PKCE -> Google OAuth -> per-patient Secret Manager refresh token -> Firestore metadata -> Gmail watch/Pub/Sub private worker -> history correlation -> Calendar/Tasks -> receipts`.

Only `healthia-one-web-demo` is public. `healthia-one-demo` remains private.
