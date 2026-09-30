import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Assemble des classes CSS conditionnelles et résout les conflits Tailwind. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
