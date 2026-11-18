const channels = document.querySelector('#channels')
const table = document.querySelector('#stats-table')
const empty = document.querySelector('#empty-channels')
const connectionError = document.querySelector('#connection-error')
const numberFormat = new Intl.NumberFormat('ru-RU')

function cell(tag, text, className) {
  const node = document.createElement(tag)
  node.textContent = text
  if (className) node.className = className
  return node
}

function channelRow(channel) {
  const row = document.createElement('tr')
  const name = cell('th', '')
  name.scope = 'row'
  const link = document.createElement('a')
  link.textContent = channel.slug
  link.href = 'https://live.vkvideo.ru/' + encodeURIComponent(channel.slug)
  link.target = '_blank'
  link.rel = 'noopener'
  name.append(link)
  const status = { true: 'В эфире', false: 'Офлайн', null: 'Нет данных' }[channel.is_online]
  row.append(
    name,
    cell('td', channel.is_active ? 'Активен' : status,
      channel.is_online ? 'online' : 'muted'),
    cell('td', channel.is_online ? numberFormat.format(channel.viewers) : '—'),
    cell('td', channel.points == null ? '—' : numberFormat.format(channel.points)),
    cell('td', numberFormat.format(Math.floor(channel.watch_time / 60)) + ' мин'),
  )
  return row
}

function render(data) {
  document.querySelector('#channel-count').textContent =
    data.total_streamers + ' всего · ' + data.online_count + ' в эфире · ' + data.active_count + ' активных'
  const hasChannels = data.streamers.length > 0
  empty.textContent = 'Статистики по каналам пока нет.'
  empty.hidden = hasChannels
  table.hidden = !hasChannels
  channels.replaceChildren(...data.streamers.map(channelRow))
}

async function poll() {
  try {
    const response = await fetch('/api/status', { cache: 'no-store' })
    if (!response.ok) throw new Error()
    render(await response.json())
    connectionError.hidden = true
  } catch {
    connectionError.textContent = 'Не удалось обновить статистику. Повторяем подключение…'
    connectionError.hidden = false
  } finally {
    setTimeout(poll, 5000)
  }
}

poll()
