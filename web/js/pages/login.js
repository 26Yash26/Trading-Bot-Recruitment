// Google sign-in, restricted to @smail.iitm.ac.in.
//
// The OAuth round trip lands back on the server, which sets an HttpOnly cookie
// and redirects — no token ever passes through the URL or through JS.

import { navigate, store } from "../main.js";
import { esc, toast } from "../ui.js";

const DENIAL_REASONS = {
  domain: "That Google account is not an @smail.iitm.ac.in address.",
  unverified: "That Google account has no verified email address.",
  state: "The sign-in link expired. Please try again.",
  token: "Google did not return a valid token. Please try again.",
  nocode: "Google did not return an authorisation code. Please try again.",
};

const googleMark = `
  <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
    <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.2l6.7-6.7C35.7 2.3 30.2 0 24 0 14.7 0 6.7 5.5 2.9 13.5l7.8 6C12.5 13.3 17.8 9.5 24 9.5z"/>
    <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v8.5h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4 7.1-10 7.1-17z"/>
    <path fill="#FBBC05" d="M10.7 28.5A14.7 14.7 0 0 1 9.5 24c0-1.6.3-3.1.8-4.5l-7.8-6A23.9 23.9 0 0 0 0 24c0 3.9.9 7.5 2.5 10.8l8.2-6.3z"/>
    <path fill="#34A853" d="M24 48c6.2 0 11.4-2 15.2-5.5l-7.5-5.8c-2 1.4-4.6 2.3-7.7 2.3-6.2 0-11.5-4.2-13.3-9.8l-8.2 6.3C6.7 42.5 14.7 48 24 48z"/>
  </svg>`;

export async function renderLogin(app) {
  const params = new URLSearchParams(location.search);
  const auth = params.get("auth");
  const reason = params.get("reason") || "";

  if (auth) {
    history.replaceState({}, "", "/login");
    if (auth === "denied" || auth === "failed") {
      toast(DENIAL_REASONS[reason] || "Sign-in failed. Please try again.", "error", 8000);
    }
  }

  if (store.me.signed_in) {
    navigate("/submit", { replace: true });
    return;
  }

  const configured = store.me.oauth_configured !== false;

  app.innerHTML = `
    <section class="mx-auto grid min-h-[70vh] max-w-md place-items-center px-5 py-16">
      <div class="panel panel-glow w-full p-8">
        <div class="flex flex-col items-center gap-3 text-center">
          <span class="grid h-12 w-12 place-items-center rounded-2xl border border-gold/40 bg-gold/10
                       font-heading text-lg font-bold text-gold">Q</span>
          <h1 class="font-heading text-xl font-bold">Sign in to compete</h1>
          <p class="text-sm text-ink-dim">
            Only <span class="font-mono text-gold">@smail.iitm.ac.in</span> accounts can submit a bot.
            The leaderboard is open to everyone.
          </p>
        </div>

        ${
          configured
            ? `<a href="/api/auth/login"
                  class="mt-8 flex w-full items-center justify-center gap-3 rounded-xl border border-line-bright
                         bg-white px-4 py-3 text-sm font-semibold text-[#1f2328] transition-all
                         hover:-translate-y-0.5 hover:shadow-lg">
                 ${googleMark} Continue with Google
               </a>`
            : `<div class="mt-8 rounded-xl border border-loss/35 bg-loss/10 px-4 py-3 text-sm text-loss">
                 Google sign-in is not configured on this server yet.
                 Set <span class="font-mono text-xs">QG_GOOGLE_CLIENT_ID</span> and
                 <span class="font-mono text-xs">QG_GOOGLE_CLIENT_SECRET</span>.
               </div>`
        }

        <p class="mt-6 text-center text-xs leading-relaxed text-ink-faint">
          We read your name, email address and nothing else — only to confirm you are at IIT Madras
          and to bind submissions to your roll number.
        </p>
      </div>

      ${
        reason && auth === "denied"
          ? `<p class="mt-5 max-w-sm text-center font-mono text-xs text-loss">${esc(
              DENIAL_REASONS[reason] || reason
            )}</p>`
          : ""
      }
    </section>`;
}
