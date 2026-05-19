<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'

const props = defineProps<{
  config: Record<string, any>
  hasDocFiles: boolean
}>()

const emit = defineEmits<{
  (e: 'update:config', val: Record<string, any>): void
}>()

// 本地深拷贝 reactive 对象——组件实例销毁时一同销毁，不受外部影响
const local = reactive<Record<string, any>>({ ...props.config })

// 用户修改 → emit 给父组件同步 cfg store
watch(local, (val) => {
  emit('update:config', { ...val })
}, { deep: true })

const showAdvanced = ref(false)
</script>

<template>
  <el-form label-position="top" class="config-form">
    <el-form-item>
      <template #label>
        后端类型 (backend)
        <el-tooltip content="hybrid: 纯文本偏多时更快；vlm: 含大量图片和复杂版式时效果更好" placement="top">
          <el-icon style="vertical-align: middle; margin-left: 4px"><QuestionFilled /></el-icon>
        </el-tooltip>
      </template>
      <el-select v-model="local.backend">
        <el-option value="hybrid-http-client" label="hybrid-http-client" />
        <el-option value="vlm-http-client" label="vlm-http-client" />
      </el-select>
    </el-form-item>

    <el-form-item label="MinerU 服务地址">
      <el-input v-model="local.mineruApi" />
    </el-form-item>

    <el-form-item label="大模型服务地址 (server_url)">
      <el-input v-model="local.serverUrl" />
    </el-form-item>

    <el-form-item>
      <template #label>
        解析方式 (parse_method)
        <el-tooltip content="auto: 自动选择；ocr: 强制OCR识别；txt: 纯文本提取" placement="top">
          <el-icon style="vertical-align: middle; margin-left: 4px"><QuestionFilled /></el-icon>
        </el-tooltip>
      </template>
      <el-select v-model="local.parseMethod">
        <el-option value="auto" label="auto" />
        <el-option value="ocr" label="ocr" />
        <el-option value="txt" label="txt" />
      </el-select>
    </el-form-item>

    <el-form-item label="语言 (lang_list)">
      <el-input v-model="local.langList" placeholder="ch / en / ch,en" />
    </el-form-item>

    <el-form-item label="输出格式">
      <el-radio-group v-model="local.outputFormat">
        <el-radio-button value="md">Markdown</el-radio-button>
        <el-radio-button value="txt">纯文本</el-radio-button>
        <el-radio-button value="html">HTML</el-radio-button>
      </el-radio-group>
    </el-form-item>

    <el-form-item label="超时时间 (秒)">
      <el-input-number v-model="local.timeout" :min="60" :max="3600" :step="60" />
      <div class="form-tip">大文件建议 600~1800 秒</div>
    </el-form-item>

    <el-form-item v-if="hasDocFiles" label="文档自动转 PDF">
      <el-switch v-model="local.autoConvert" />
      <div class="form-tip">关闭后，Word/PPT/Excel 文件需在任务列表手动转换</div>
    </el-form-item>

    <el-link type="primary" :underline="false" @click="showAdvanced = !showAdvanced" style="margin: 4px 0">
      {{ showAdvanced ? '收起高级选项 ▲' : '展开高级选项 ▼' }}
    </el-link>

    <template v-if="showAdvanced">
      <el-form-item label="公式识别"><el-switch v-model="local.formulaEnable" /></el-form-item>
      <el-form-item label="表格识别"><el-switch v-model="local.tableEnable" /></el-form-item>
      <el-form-item label="返回 Markdown"><el-switch v-model="local.returnMd" /></el-form-item>
      <el-form-item label="返回 middle_json"><el-switch v-model="local.returnMiddleJson" /></el-form-item>
      <el-form-item label="返回模型输出"><el-switch v-model="local.returnModelOutput" /></el-form-item>
      <el-form-item label="返回 content_list"><el-switch v-model="local.returnContentList" /></el-form-item>
      <el-form-item label="返回图片"><el-switch v-model="local.returnImages" /></el-form-item>
      <el-form-item label="ZIP 格式响应"><el-switch v-model="local.responseFormatZip" /></el-form-item>
      <el-form-item label="替换图片 URL"><el-switch v-model="local.replaceImageUrl" /></el-form-item>
      <el-form-item label="起始页码"><el-input-number v-model="local.startPageId" :min="0" :step="1" /></el-form-item>
      <el-form-item label="结束页码"><el-input-number v-model="local.endPageId" :min="0" :step="1" /></el-form-item>
    </template>
  </el-form>
</template>

<style scoped>
.config-form { display: flex; flex-direction: column; gap: 2px; }
.form-tip { font-size: 12px; color: #909399; margin-top: 2px; }
</style>
