/**
 * API client service for CodeCourt backend endpoints.
 */

import type {
  FeedbackItem,
  FeedbackSummary,
  ReviewDetail,
  ReviewItem,
  ReviewListResponse,
  ReviewTriggerRequest,
} from '../types/review'

const BASE_URL = '/api'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`
    try {
      const errorJson = await res.json()
      if (errorJson?.detail) {
        detail = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail)
      }
    } catch {
      // Non-JSON response body
    }
    throw new ApiError(detail, res.status)
  }
  return res.json() as Promise<T>
}

export async function fetchReviews(
  statusFilter?: string,
  skip = 0,
  limit = 50,
): Promise<ReviewListResponse> {
  const params = new URLSearchParams()
  if (statusFilter && statusFilter !== 'all') {
    params.set('status', statusFilter)
  }
  params.set('skip', skip.toString())
  params.set('limit', limit.toString())

  const response = await fetch(`${BASE_URL}/reviews?${params.toString()}`)
  return handleResponse<ReviewListResponse>(response)
}

export async function fetchReviewDetail(reviewId: number): Promise<ReviewDetail> {
  const response = await fetch(`${BASE_URL}/reviews/${reviewId}`)
  return handleResponse<ReviewDetail>(response)
}

export async function fetchReviewDiff(reviewId: number): Promise<{ diff_text: string | null }> {
  const response = await fetch(`${BASE_URL}/reviews/${reviewId}/diff`)
  return handleResponse<{ diff_text: string | null }>(response)
}

export async function triggerReview(payload: ReviewTriggerRequest): Promise<ReviewItem> {
  const response = await fetch(`${BASE_URL}/reviews/trigger`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return handleResponse<ReviewItem>(response)
}

export async function submitFindingFeedback(
  findingId: number,
  action: 'accepted' | 'dismissed',
  reason?: string,
): Promise<FeedbackItem> {
  const response = await fetch(`${BASE_URL}/findings/${findingId}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, reason }),
  })
  return handleResponse<FeedbackItem>(response)
}

export async function fetchReviewFeedback(
  reviewId: number,
): Promise<{ review_id: number; summary: FeedbackSummary; items: FeedbackItem[] }> {
  const response = await fetch(`${BASE_URL}/reviews/${reviewId}/feedback`)
  return handleResponse<{ review_id: number; summary: FeedbackSummary; items: FeedbackItem[] }>(response)
}

export async function fetchHealth(): Promise<{ status: string; timestamp: string }> {
  const response = await fetch(`${BASE_URL}/health`)
  return handleResponse<{ status: string; timestamp: string }>(response)
}

export async function fetchBenchmarkOverview(
  split = 'test',
  refresh = false,
): Promise<import('../types/eval').BenchmarkOverview> {
  const params = new URLSearchParams({ split })
  if (refresh) params.set('refresh', 'true')
  const response = await fetch(`${BASE_URL}/eval/benchmark?${params.toString()}`)
  return handleResponse<import('../types/eval').BenchmarkOverview>(response)
}

export async function fetchFailureAnalysis(): Promise<import('../types/eval').FailureAnalysisData> {
  const response = await fetch(`${BASE_URL}/eval/failure-analysis`)
  return handleResponse<import('../types/eval').FailureAnalysisData>(response)
}

