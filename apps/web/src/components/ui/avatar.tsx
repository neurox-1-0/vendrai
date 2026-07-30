import * as React from "react"

export interface AvatarProps {
  name: string;
  src?: string;
  size?: 'sm' | 'md' | 'lg';
  badge?: React.ReactNode;
  className?: string;
}

const SIZE_CLASSES = {
  sm: "h-8 w-8 text-xs",
  md: "h-10 w-10 text-sm",
  lg: "h-14 w-14 text-lg",
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return `${parts[0]![0]}${parts.at(-1)![0]}`.toUpperCase();
}

/**
 * Circular avatar with an initials fallback. `src` is accepted for
 * completeness, but no per-user photo directory exists in the API today --
 * in practice every call site renders the fallback.
 */
function Avatar({ name, src, size = 'md', badge, className }: AvatarProps) {
  return (
    <span className={`relative inline-flex shrink-0 ${className ?? ""}`}>
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element -- small, dynamic avatar source; next/image is unnecessary overhead here
        <img
          src={src}
          alt=""
          className={`rounded-full object-cover ${SIZE_CLASSES[size]}`}
        />
      ) : (
        <span
          aria-hidden="true"
          className={`flex items-center justify-center rounded-full bg-[var(--color-accent-light)] font-bold text-[var(--color-accent-dark)] ${SIZE_CLASSES[size]}`}
        >
          {initials(name)}
        </span>
      )}
      <span className="sr-only">{name}</span>
      {badge && (
        <span className="absolute -bottom-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full ring-2 ring-white">
          {badge}
        </span>
      )}
    </span>
  );
}

export { Avatar };
