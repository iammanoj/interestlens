/**
 * API client for InterestLens backend
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function analyzePageAPI(
  request: any,
  token: string | null
): Promise<any> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}/analyze_page`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      page_url: request.pageUrl,
      dom_outline: {
        title: request.domOutline.title,
        headings: request.domOutline.headings,
        main_text_excerpt: request.domOutline.mainTextExcerpt,
      },
      items: request.items.map((item: any) => ({
        id: item.id,
        href: item.href,
        text: item.text,
        snippet: item.snippet,
        bbox: item.bbox,
        thumbnail_base64: item.thumbnailBase64,
      })),
      screenshot_base64: request.screenshotBase64,
    }),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  const data = await response.json();

  return {
    items: data.items,
    pageTopics: data.page_topics,
    profileSummary: data.profile_summary
      ? { topTopics: data.profile_summary.top_topics }
      : undefined,
    weaveTraceUrl: data.weave_trace_url,
  };
}

export async function logEventAPI(
  event: string,
  itemId: string,
  pageUrl: string,
  itemData: any,
  token: string
): Promise<void> {
  await fetch(`${API_BASE}/event`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      event,
      item_id: itemId,
      page_url: pageUrl,
      timestamp: Date.now(),
      item_data: {
        text: itemData.text,
        topics: itemData.topics,
      },
    }),
  });
}

export async function getUserInfoAPI(token: string): Promise<any> {
  const response = await fetch(`${API_BASE}/auth/me`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to get user info');
  }

  return response.json();
}
