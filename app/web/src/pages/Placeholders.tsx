import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";

export function LibraryPage() {
  return (
    <EmptyState
      message="Connect Spotify or YouTube to sync your likes — account connections arrive with M3."
      action={
        <Link
          to="/settings#accounts"
          className="inline-block rounded-[6px] border border-line px-4 py-2 text-[0.9rem] hover:bg-bg2"
        >
          See Accounts in Settings
        </Link>
      }
    />
  );
}

