<template>
  <div class="help-container">
    <n-layout has-sider style="min-height: 60vh">
      <!-- Sidebar: categories & article list -->
      <n-layout-sider bordered width="240" style="padding: 12px">
        <n-spin :show="loading">
          <div v-for="cat in categories" :key="cat.category" style="margin-bottom: 16px">
            <div class="cat-label">{{ cat.label }}</div>
            <div v-for="art in cat.articles" :key="art.slug" class="art-link"
              :class="{ active: currentSlug === art.slug }" @click="loadArticle(art.slug)">
              {{ art.title }}
            </div>
            <n-text v-if="!cat.articles.length" depth="3" style="font-size: 13px">暂无文章</n-text>
          </div>
          <n-empty v-if="!categories.length && !loading" description="暂无帮助内容" />
        </n-spin>
      </n-layout-sider>

      <!-- Main content: article -->
      <n-layout-content style="padding: 24px 32px">
        <template v-if="article">
          <h2 style="margin-top: 0">{{ article.title }}</h2>
          <div class="markdown-body" v-html="renderedContent"></div>
        </template>
        <n-empty v-else-if="!loading" description="请从左侧选择文章" />
      </n-layout-content>
    </n-layout>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { marked } from 'marked'
import { getHelpCategories, getHelpArticle } from '../api/help'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const categories = ref([])
const article = ref(null)
const currentSlug = ref(null)
const loading = ref(false)

const renderedContent = computed(() => {
  if (!article.value?.content) return ''
  return marked(article.value.content)
})

async function fetchCategories() {
  loading.value = true
  try {
    const { data } = await getHelpCategories()
    categories.value = data
  } catch {
    message.error('获取帮助分类失败')
  } finally {
    loading.value = false
  }
}

async function loadArticle(slug) {
  currentSlug.value = slug
  router.replace(`/help/${slug}`)
  try {
    const { data } = await getHelpArticle(slug)
    article.value = data
  } catch {
    message.error('获取文章失败')
    article.value = null
  }
}

onMounted(async () => {
  await fetchCategories()
  // If URL has a slug, load it; otherwise load first article
  const slug = route.params.slug
  if (slug) {
    await loadArticle(slug)
  } else if (categories.value.length > 0 && categories.value[0].articles.length > 0) {
    await loadArticle(categories.value[0].articles[0].slug)
  }
})

watch(() => route.params.slug, (newSlug) => {
  if (newSlug && newSlug !== currentSlug.value) {
    loadArticle(newSlug)
  }
})
</script>

<style scoped>
.help-container {
  max-width: 960px;
  margin: 0 auto;
}

.cat-label {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 6px;
  color: var(--n-text-color);
}

.art-link {
  padding: 4px 8px;
  font-size: 13px;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.2s;
  color: var(--n-text-color-2);
}

.art-link:hover {
  background: var(--n-color-hover);
}

.art-link.active {
  background: var(--n-color-hover);
  color: var(--n-primary-color);
  font-weight: 500;
}

.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--n-text-color);
}

.markdown-body :deep(h1) { font-size: 1.6em; margin: 1em 0 0.5em; }
.markdown-body :deep(h2) { font-size: 1.3em; margin: 0.8em 0 0.4em; }
.markdown-body :deep(h3) { font-size: 1.1em; margin: 0.6em 0 0.3em; }
.markdown-body :deep(p) { margin: 0.5em 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 1.5em; }
.markdown-body :deep(li) { margin: 0.2em 0; }
.markdown-body :deep(code) {
  background: var(--n-color-modal);
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 0.9em;
}
.markdown-body :deep(pre) {
  background: var(--n-color-modal);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
}
.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--n-border-color);
  padding-left: 12px;
  margin: 0.5em 0;
  color: var(--n-text-color-3);
}
.markdown-body :deep(a) {
  color: var(--n-primary-color);
  text-decoration: none;
}
.markdown-body :deep(a:hover) {
  text-decoration: underline;
}
.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.5em 0;
}
.markdown-body :deep(th), .markdown-body :deep(td) {
  border: 1px solid var(--n-border-color);
  padding: 6px 12px;
  text-align: left;
}
.markdown-body :deep(th) {
  background: var(--n-color-modal);
}
</style>
