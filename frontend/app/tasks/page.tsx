"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Tasks are not a destination any more — they are what a day is made of, so
 * they live in the Planner alongside classes, coursework and deadlines.
 *
 * The route is kept rather than deleted so existing links, bookmarks and any
 * saved PWA shortcut still land somewhere sensible.
 */
export default function TasksRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace("/planner"); }, [router]);
  return null;
}
