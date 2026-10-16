import api from './client'

export function getHelpCategories() {
  return api.get('/help/categories')
}

export function getHelpArticle(slug) {
  return api.get(`/help/articles/${slug}`)
}
