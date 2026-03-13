import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

const SITE_NAME = 'TRUSEO';
const DEFAULT_TITLE = 'TRUSEO — Optimize visibility in LLM answers';
const DEFAULT_DESCRIPTION =
  'Self-learning platform to monitor how ChatGPT, Perplexity, and Claude cite your domain, turn gaps into content briefs, and improve visibility in AI-generated answers.';

type MetaEntry = {
  title: string;
  description: string;
};

const PATH_META: Record<string, MetaEntry> = {
  '/': {
    title: `${SITE_NAME} — Optimize visibility in LLM answers`,
    description: DEFAULT_DESCRIPTION,
  },
  '/try': {
    title: `Try it free — ${SITE_NAME}`,
    description:
      'Enter your website to see how LLMs cite you. We discover your domain, generate prompts, and run monitoring across ChatGPT, Perplexity, Claude, and Gemini. No sign-up required.',
  },
  '/how-it-works': {
    title: `How it works — ${SITE_NAME}`,
    description:
      'Learn how TRUSEO discovers your domain, generates prompts, monitors LLM answers for citations and brand mentions, and turns gaps into content briefs in an agentic loop.',
  },
  '/trial-directory': {
    title: `Trial directory — ${SITE_NAME}`,
    description: 'Browse domains that have been analyzed in free trials. View results and visibility across LLMs.',
  },
  '/signin': {
    title: `Sign in — ${SITE_NAME}`,
    description: `Sign in to your ${SITE_NAME} account to manage domains, prompts, monitoring, and content briefs.`,
  },
  '/signup': {
    title: `Sign up — ${SITE_NAME}`,
    description: `Create your ${SITE_NAME} account to track how LLMs cite your domain and improve visibility.`,
  },
  '/domains': {
    title: `Domains — ${SITE_NAME}`,
    description: 'Manage your tracked domains. Add domains to monitor how LLMs cite and mention your brand.',
  },
  '/prompts': {
    title: `Prompts — ${SITE_NAME}`,
    description: 'View and manage prompts used for monitoring. See visibility (cited, brand mentioned, competitor-only) per model.',
  },
  '/prompts/generate': {
    title: `Generate prompts — ${SITE_NAME}`,
    description: 'Generate high-intent prompts from your domain profiles for LLM monitoring.',
  },
  '/briefs': {
    title: `Briefs — ${SITE_NAME}`,
    description: 'Content briefs generated from visibility gaps. Turn uncited prompts into content opportunities.',
  },
  '/drafts': {
    title: `Drafts — ${SITE_NAME}`,
    description: 'Content drafts created from briefs. Edit and publish to improve LLM citations.',
  },
  '/content-sources': {
    title: `Content sources — ${SITE_NAME}`,
    description: 'Manage content sources and distribution channels for publishing drafts.',
  },
  '/prompt-generation': {
    title: `Prompt generation — ${SITE_NAME}`,
    description: 'Configure and run prompt generation for your domains.',
  },
  '/monitoring': {
    title: `Monitoring — ${SITE_NAME}`,
    description: 'Configure and run LLM monitoring. See execution history and visibility per model.',
  },
  '/reports': {
    title: `Reports — ${SITE_NAME}`,
    description: 'Citation trends and monitoring reports across your domains and prompts.',
  },
  '/settings': {
    title: `Settings — ${SITE_NAME}`,
    description: `Manage your ${SITE_NAME} account, API keys, and model settings for OpenAI, Anthropic, Perplexity, and Gemini.`,
  },
};

function getMetaForPath(pathname: string): MetaEntry {
  const exact = PATH_META[pathname];
  if (exact) return exact;

  if (pathname.startsWith('/try/') && pathname.length > 5) {
    const slug = pathname.slice(5).replace(/-/g, '.');
    return {
      title: `Trial results: ${slug} — ${SITE_NAME}`,
      description: `View trial analysis and LLM visibility for ${slug}. Domain discovery, prompts, and citation results across models.`,
    };
  }
  if (pathname.startsWith('/prompts/') && pathname !== '/prompts/generate') {
    const id = pathname.split('/')[2];
    return {
      title: `Prompt ${id} — ${SITE_NAME}`,
      description: `Prompt detail and visibility across monitoring runs and models.`,
    };
  }
  if (pathname.startsWith('/briefs/')) {
    const id = pathname.split('/')[2];
    return {
      title: `Brief ${id} — ${SITE_NAME}`,
      description: 'Content brief from visibility gaps. Use it to create content that improves LLM citations.',
    };
  }
  if (pathname.startsWith('/drafts/')) {
    if (pathname.endsWith('/publish')) {
      return {
        title: `Publish draft — ${SITE_NAME}`,
        description: 'Publish your draft to configured content channels.',
      };
    }
    const id = pathname.split('/')[2];
    return {
      title: `Draft ${id} — ${SITE_NAME}`,
      description: 'Edit and publish your content draft.',
    };
  }
  if (pathname.startsWith('/monitoring/executions/')) {
    const id = pathname.split('/').pop();
    return {
      title: `Monitoring run ${id} — ${SITE_NAME}`,
      description: 'Execution detail: runs by model, prompt visibility, and settings.',
    };
  }

  return { title: DEFAULT_TITLE, description: DEFAULT_DESCRIPTION };
}

function setMetaTag(
  attribute: 'name' | 'property',
  key: string,
  value: string
): void {
  let el = document.querySelector(
    `meta[${attribute}="${key}"]`
  ) as HTMLMetaElement | null;
  if (!el) {
    el = document.createElement('meta');
    el.setAttribute(attribute, key);
    document.head.appendChild(el);
  }
  el.setAttribute('content', value);
}

export function PageMeta() {
  const { pathname } = useLocation();
  const { title, description } = getMetaForPath(pathname);

  useEffect(() => {
    document.title = title;
    setMetaTag('name', 'description', description);
    setMetaTag('property', 'og:title', title);
    setMetaTag('property', 'og:description', description);
    setMetaTag('property', 'og:type', 'website');
    setMetaTag('property', 'og:site_name', SITE_NAME);
    if (typeof window !== 'undefined' && window.location.href) {
      setMetaTag('property', 'og:url', window.location.href);
    }
    setMetaTag('name', 'twitter:card', 'summary_large_image');
    setMetaTag('name', 'twitter:title', title);
    setMetaTag('name', 'twitter:description', description);
  }, [pathname, title, description]);

  return null;
}
