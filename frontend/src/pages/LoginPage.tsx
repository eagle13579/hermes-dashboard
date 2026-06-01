import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      const data = await res.json()
      if (res.ok && data.access_token) {
        localStorage.setItem('token', data.access_token)
        localStorage.setItem('user', JSON.stringify(data.user))
        navigate('/')
      } else {
        setError(data.detail || '登录失败')
      }
    } catch (err) {
      setError('网络错误，请重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="bg-card border border-border rounded-lg p-8 w-full max-w-md">
        <h1 className="text-2xl font-bold text-foreground mb-2">Hermes Dashboard</h1>
        <p className="text-muted-foreground mb-6">AI统一开发指挥中心</p>
        
        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-sm text-foreground mb-1">用户名</label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              className="w-full px-3 py-2 bg-background border border-border rounded text-foreground"
              placeholder="admin"
              required
            />
          </div>
          <div>
            <label className="block text-sm text-foreground mb-1">密码</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full px-3 py-2 bg-background border border-border rounded text-foreground"
              placeholder="admin123"
              required
            />
          </div>
          {error && <p className="text-red-500 text-sm">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-primary text-primary-foreground rounded hover:opacity-90 disabled:opacity-50"
          >
            {loading ? '登录中...' : '登 录'}
          </button>
        </form>
        <p className="text-xs text-muted-foreground mt-4 text-center">
          默认管理员: admin / admin123
        </p>
      </div>
    </div>
  )
}
