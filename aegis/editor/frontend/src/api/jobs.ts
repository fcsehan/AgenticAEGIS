import { requestJson } from "./client";
interface Job<T> {
  id: string;
  status: string;
  result: T | null;
  error: string;
}
export async function runJob<T>(
  url: string,
  body: unknown,
  onJob: (id: string) => void,
): Promise<T> {
  let job = await requestJson<Job<T>>(url, {
    method: "POST",
    body: JSON.stringify(body),
  });
  onJob(job.id);
  while (job.status === "queued" || job.status === "running") {
    await new Promise((resolve) => setTimeout(resolve, 500));
    job = await requestJson<Job<T>>(`/api/jobs/${job.id}`);
  }
  if (job.status !== "succeeded" || !job.result)
    throw new Error(job.error || `Auftrag ${job.status}`);
  return job.result;
}
