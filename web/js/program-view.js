// program-view.js
// 程序视图：显示 main.py 代码，支持运行、断点调试和高亮当前执行行

import { mqttClient } from './mqtt-client.js';

export default {
    name: 'ProgramView',
    inject: ['isLoggedIn'],
    template: `
    <div class="panel pv-panel">
        <div class="pv-code-wrap">
            <div class="code-block" ref="codeBlock">
                <div
                    v-for="(line, idx) in codeLines"
                    :key="idx"
                    :class="['code-line', {
                        'code-line-active': idx + 1 === currentLine,
                        'code-line-breakpoint': hasBreakpoint(idx + 1)
                    }]"
                    :ref="idx + 1 === currentLine ? 'activeLine' : null"
                >
                    <button
                        type="button"
                        :class="['line-num', { 'line-num-breakpoint': hasBreakpoint(idx + 1) }]"
                        :title="hasBreakpoint(idx + 1) ? '点击取消断点' : '点击设置断点'"
                        @click.stop="toggleBreakpoint(idx + 1)"
                    >{{ idx + 1 }}</button>
                    <span class="line-content">{{ line || ' ' }}</span>
                </div>
            </div>
        </div>

        <div class="pv-actionbar">
            <div class="pv-stepinfo">
                <span v-if="currentLine > 0">
                    当前执行: 第 <span class="step-line-no">{{ currentLine }}</span> 行
                    <span class="step-code">{{ codeLines[currentLine - 1] }}</span>
                </span>
                <span v-else class="pv-idle">就绪</span>
            </div>
            <div class="program-actions">
                <button class="program-btn file-btn" @click="openFileList"><ui-icon name="folder"></ui-icon>文件</button>
                <button
                    class="program-btn run-btn"
                    :class="{ active: running && !breakpointPaused }"
                    :disabled="running && !breakpointPaused"
                    @click="runProgram">
                    <ui-icon name="play"></ui-icon>
                    {{ running && !breakpointPaused ? '运行中...' : '运行' }}
                </button>
                <button
                    class="program-btn pause-btn"
                    :class="{ active: paused || pausePending }"
                    :disabled="!running || paused || pausePending || breakpointPaused"
                    @click="pauseProgram">
                    <ui-icon name="pause"></ui-icon>
                    暂停
                </button>
                <button
                    class="program-btn resume-btn"
                    :disabled="!running || breakpointPaused || (!paused && !pausePending)"
                    @click="resumeProgram">
                    <ui-icon name="play"></ui-icon>
                    恢复
                </button>
                <label
                    class="program-debug-toggle"
                    :class="{ active: debugEnabled, disabled: running }"
                    title="启用后，运行到断点时暂停">
                    <input type="checkbox" v-model="debugEnabled" :disabled="running" />
                    <ui-icon name="bug"></ui-icon>
                    <span>调试</span>
                </label>
                <button
                    class="program-btn next-btn"
                    :disabled="!debugEnabled || !breakpointPaused"
                    @click="nextLine">
                    <ui-icon name="next"></ui-icon>
                    下一行
                </button>
                <button
                    class="program-btn stop-btn"
                    :disabled="!running"
                    @click="stopProgram">
                    <ui-icon name="stop"></ui-icon>
                    停止程序
                </button>
            </div>
        </div>

        <!-- 文件列表弹窗 -->
        <div v-if="showFileList" class="save-overlay" @click.self="closeFileList">
            <div class="save-dialog save-dialog-files">
                <h6 class="pv-dialog-title">程序文件</h6>

                <!-- 状态提示 -->
                <div v-if="fileMsg" :style="{color: fileMsgColor, fontSize:'13px', marginBottom:'8px', minHeight:'18px'}">{{ fileMsg }}</div>

                <!-- 隐藏的文件选择器 -->
                <input type="file" ref="fileInput" accept=".py" style="display:none;" @change="onFileSelected" />

                <!-- 文件列表 -->
                <div v-if="programFiles.length === 0" class="pv-empty-tip">
                    暂无文件
                </div>
                <ul v-else class="file-list" style="margin-bottom:12px; max-height:280px; overflow-y:auto;">
                    <li
                        v-for="f in programFiles"
                        :key="f"
                        :class="{'file-selected': selectedFile === f}"
                        @click="selectedFile = f"
                        style="cursor:pointer;"
                    >
                        {{ f }}
                    </li>
                </ul>

                <!-- 底部按钮栏 -->
                <div class="dialog-btn-bar dialog-btn-bar-noflexwrap">
                    <button class="nav-btn dialog-btn" @click="openCreateDialog" style="background:#00499d; color:#fff;">
                        <ui-icon name="plus"></ui-icon>新建
                    </button>
                    <button class="nav-btn dialog-btn" @click="triggerFileSelect" :disabled="uploading" style="background:#00499d; color:#fff;">
                        <ui-icon name="upload"></ui-icon>
                        {{ uploading ? '上传中...' : '上传' }}
                    </button>
                    <button class="nav-btn dialog-btn" @click="openFile" :disabled="!selectedFile || openingFile || running" style="background:#00499d; color:#fff;">
                        <ui-icon name="folder-open"></ui-icon>{{ openingFile ? '打开中...' : '打开' }}
                    </button>
                    <button class="nav-btn dialog-btn" @click="openEditFile" :disabled="!selectedFile || editingFile" style="background:#00499d; color:#fff;">
                        <ui-icon name="edit"></ui-icon>
                        {{ editingFile ? '加载中...' : '修改' }}
                    </button>
                    <button class="nav-btn dialog-btn" @click="downloadFile" :disabled="!selectedFile || downloading" style="background:#00499d; color:#fff;">
                        <ui-icon name="download"></ui-icon>
                        {{ downloading ? '下载中...' : '下载' }}
                    </button>
                    <button class="nav-btn dialog-btn" @click="deleteFile" :disabled="!selectedFile || selectedFile === 'main.py'" style="background:#00499d; color:#fff;">
                        <ui-icon name="trash"></ui-icon>删除
                    </button>
                    <button class="nav-btn dialog-btn" @click="closeFileList"><ui-icon name="x"></ui-icon>关闭</button>
                </div>
            </div>
        </div>

        <!-- 新建文件弹窗 -->
        <div v-if="showCreateDialog" class="save-overlay" @click.self="closeCreateDialog">
            <div class="save-dialog save-dialog-create">
                <h6 class="pv-dialog-title">新建程序文件</h6>
                <label class="pv-create-label" for="pv-create-name">文件名</label>
                <input
                    id="pv-create-name"
                    ref="createNameInput"
                    v-model.trim="createFileName"
                    class="pv-create-input"
                    type="text"
                    autocomplete="off"
                    spellcheck="false"
                    placeholder="例如：my_program.py"
                    @keyup.enter="createFile"
                />
                <div class="pv-create-hint">未填写 .py 后缀时会自动补全；不能覆盖已有文件。</div>
                <div v-if="createMsg" :style="{color: createMsgColor, fontSize:'13px', marginTop:'8px', minHeight:'18px'}">{{ createMsg }}</div>
                <div class="dialog-btn-bar dialog-btn-bar-noflexwrap" style="justify-content:flex-end;">
                    <button class="nav-btn dialog-btn" @click="closeCreateDialog" :disabled="creating"><ui-icon name="x"></ui-icon>取消</button>
                    <button class="nav-btn dialog-btn" @click="createFile" :disabled="creating" style="background:#00499d; color:#fff;">
                        <ui-icon name="plus"></ui-icon>
                        {{ creating ? '创建中...' : '创建' }}
                    </button>
                </div>
            </div>
        </div>

        <!-- 代码编辑弹窗 -->
        <div v-if="showEditDialog" class="save-overlay" @click.self="cancelEdit">
            <div class="save-dialog save-dialog-edit">
                <h6 class="pv-dialog-title">修改文件 — {{ editFileName }}</h6>
                <textarea
                    ref="editTextarea"
                    v-model="editContent"
                    class="pv-edit-textarea"
                    spellcheck="false"
                    placeholder="代码加载中..."
                ></textarea>
                <div v-if="editMsg" :style="{color: editMsgColor, fontSize:'13px', marginTop:'8px', minHeight:'18px'}">{{ editMsg }}</div>
                <div class="dialog-btn-bar dialog-btn-bar-noflexwrap" style="justify-content:flex-end;">
                    <button class="nav-btn dialog-btn" @click="cancelEdit"><ui-icon name="x"></ui-icon>取消</button>
                    <button class="nav-btn dialog-btn" @click="saveEdit" :disabled="editSaving" style="background:#00499d; color:#fff;">
                        <ui-icon name="save"></ui-icon>
                        {{ editSaving ? '保存中...' : '保存' }}
                    </button>
                </div>
            </div>
        </div>
        <!-- 确认弹窗 -->
        <div v-if="confirmDialog.visible" class="save-overlay" @click.self="cancelConfirm">
            <div class="save-dialog" style="width:360px;">
                <h6 :style="{marginBottom:'16px', color: confirmDialog.type === 'run' ? '#00499d' : '#00499d'}">
                    {{ confirmDialog.title }}
                </h6>
                <div style="color:#ccc; margin-bottom:20px; line-height:1.6; white-space:pre-line;">{{ confirmDialog.message }}</div>
                <div class="step-actions">
                    <button class="nav-btn" @click="cancelConfirm"><ui-icon name="x"></ui-icon>取消</button>
                    <button
                        class="nav-btn"
                        :style="{background: confirmDialog.type === 'run' ? '#00499d' : '#00499d', color:'#fff'}"
                        @click="confirmAction">
                        <ui-icon name="check"></ui-icon>确定
                    </button>
                </div>
            </div>
        </div>
    </div>
    `,
    data() {
        return {
            code: '// 点击「读取代码」加载程序',
            currentLine: 0,
            debugEnabled: false,
            running: false,
            paused: false,
            pausePending: false,
            breakpointPaused: false,
            breakpoints: [],
            showFileList: false,
            programFiles: [],
            selectedFile: '',
            currentFileName: 'main.py',
            confirmDialog: { visible: false, type: '', title: '', message: '', action: null },
            uploading: false,
            downloading: false,
            openingFile: false,
            pendingOpenFile: '',
            fileMsg: '',
            fileMsgColor: '#00499d',
            showCreateDialog: false,
            createFileName: '',
            creating: false,
            createMsg: '',
            createMsgColor: '#00499d',
            showEditDialog: false,
            editFileName: '',
            editContent: '',
            editSaving: false,
            editingFile: false,
            editMsg: '',
            editMsgColor: '#00499d'
        };
    },
    computed: {
        codeLines() {
            return this.code.split('\n');
        }
    },
    watch: {
        currentLine(newVal) {
            if (newVal > 0) {
                this.$nextTick(() => {
                    this.scrollToActiveLine();
                });
            }
        }
    },
    methods: {
        readCode() {
            mqttClient.publishRuntimeDebug('codes');
            console.log('[程序] 已请求读取代码');
        },
        hasBreakpoint(lineNumber) {
            return this.breakpoints.includes(lineNumber);
        },
        toggleBreakpoint(lineNumber) {
            const breakpoints = this.breakpoints.slice();
            const index = breakpoints.indexOf(lineNumber);
            if (index >= 0) {
                breakpoints.splice(index, 1);
            } else {
                breakpoints.push(lineNumber);
                breakpoints.sort((left, right) => left - right);
            }
            this.breakpoints = breakpoints;
            mqttClient.publishProgramControl('set_breakpoints', { lines: breakpoints });
            console.log('[程序] 已更新断点:', breakpoints);
        },
        openFileList() {
            mqttClient.publishRuntimeDebug('read_files');
            this.showFileList = true;
            this.selectedFile = '';
            this.fileMsg = '';
            console.log('[程序] 已请求文件列表');
        },
        closeFileList() {
            this.showFileList = false;
            this.selectedFile = '';
            this.fileMsg = '';
        },
        showFileMsg(msg, isError = false) {
            this.fileMsg = msg;
            this.fileMsgColor = isError ? '#00499d' : '#00499d';
            if (msg) {
                setTimeout(() => { this.fileMsg = ''; }, 3000);
            }
        },
        triggerFileSelect() {
            this.$refs.fileInput.click();
        },
        openCreateDialog() {
            this.createFileName = '';
            this.createMsg = '';
            this.creating = false;
            this.showCreateDialog = true;
            this.$nextTick(() => {
                if (this.$refs.createNameInput) {
                    this.$refs.createNameInput.focus();
                }
            });
        },
        closeCreateDialog() {
            if (this.creating) return;
            this.showCreateDialog = false;
            this.createFileName = '';
            this.createMsg = '';
        },
        showCreateMsg(msg, isError = false) {
            this.createMsg = msg;
            this.createMsgColor = isError ? '#00499d' : '#00499d';
        },
        createFile() {
            if (this.creating) return;
            let filename = this.createFileName.trim();
            if (!filename) {
                this.showCreateMsg('请输入文件名', true);
                return;
            }
            if (!filename.toLowerCase().endsWith('.py')) {
                filename += '.py';
            }
            if (this.programFiles.includes(filename)) {
                this.showCreateMsg('文件已存在，不能覆盖: ' + filename, true);
                return;
            }

            const content = [
                '#!/usr/bin/env python3',
                '"""G2 用户程序。"""',
                '',
                'from runtime2 import G2',
                '',
                '',
                'with G2() as 机器人:',
                '    pass',
                ''
            ].join('\n');
            this.creating = true;
            this.createMsg = '';
            if (this._createTimer) clearTimeout(this._createTimer);
            this._createTimer = setTimeout(() => {
                if (this.creating) {
                    this.creating = false;
                    this.showCreateMsg('创建超时，请检查服务是否正常', true);
                }
            }, 10000);
            mqttClient.publishProgramControl('create', { filename, content });
            console.log('[程序] 已发送新建请求:', filename);
        },
        onFileSelected(event) {
            const file = event.target.files[0];
            if (!file) return;
            if (!file.name.endsWith('.py')) {
                this.showFileMsg('只支持 .py 文件', true);
                event.target.value = '';
                return;
            }
            this.uploading = true;
            this.fileMsg = '';
            if (this._uploadTimer) clearTimeout(this._uploadTimer);
            this._uploadTimer = setTimeout(() => {
                if (this.uploading) {
                    this.uploading = false;
                    this.showFileMsg('上传超时，请检查服务是否正常', true);
                }
            }, 10000);
            const reader = new FileReader();
            reader.onload = (e) => {
                const content = e.target.result;
                mqttClient.publishProgramControl('upload', {
                    filename: file.name,
                    content: content
                });
                console.log('[程序] 已发送上传请求:', file.name, content.length, '字符');
            };
            reader.onerror = () => {
                this.uploading = false;
                if (this._uploadTimer) clearTimeout(this._uploadTimer);
                this.showFileMsg('文件读取失败', true);
            };
            reader.readAsText(file, 'utf-8');
            event.target.value = '';
        },
        onUploadResult(data) {
            if (data && data.command === 'create') {
                this.creating = false;
                if (this._createTimer) clearTimeout(this._createTimer);
                if (data.success) {
                    const filename = data.filename;
                    this.showCreateDialog = false;
                    this.createFileName = '';
                    this.createMsg = '';
                    this.selectedFile = filename;
                    this.showFileMsg('已新建: ' + filename);
                    console.log('[程序] 新建成功:', filename);
                    this.openEditFile();
                } else {
                    this.showCreateMsg('新建失败: ' + (data.error || '未知错误'), true);
                    console.error('[程序] 新建失败:', data.error);
                }
                return;
            }
            this.uploading = false;
            this.editSaving = false;
            if (this._uploadTimer) clearTimeout(this._uploadTimer);
            if (this._editSaveTimer) clearTimeout(this._editSaveTimer);
            if (data && data.success) {
                if (this.showEditDialog && this.editFileName === data.filename) {
                    this.showEditMsg('保存成功: ' + data.filename);
                    this.showFileMsg('保存成功: ' + data.filename);
                    setTimeout(() => {
                        this.cancelEdit();
                        if (data.filename === this.currentFileName) {
                            // 当前显示的是该用户程序复制出的 main.py；保存源文件后
                            // 重新复制一次，确保主编辑区与最新内容保持一致。
                            mqttClient.publishRuntimeDebug('copy', data.filename);
                            setTimeout(() => this.readCode(), 300);
                        }
                        mqttClient.publishProgramControl('read_files');
                    }, 500);
                } else {
                    this.showFileMsg('成功上传: ' + data.filename);
                    this.selectedFile = data.filename;
                }
                console.log('[程序] 上传成功:', data.filename);
            } else {
                const errMsg = '上传失败: ' + (data && data.error ? data.error : '未知错误');
                if (this.showEditDialog) {
                    this.showEditMsg(errMsg, true);
                } else {
                    this.showFileMsg(errMsg, true);
                }
                console.error('[程序] 上传失败');
            }
        },
        openFile() {
            if (!this.selectedFile) return;
            if (this.running) {
                this.showFileMsg('程序正在运行，请先停止程序', true);
                return;
            }
            this.openingFile = true;
            this.pendingOpenFile = this.selectedFile;
            this.fileMsg = '';
            mqttClient.publishRuntimeDebug('copy', this.pendingOpenFile);
            console.log('[程序] 已请求打开', this.pendingOpenFile);
        },
        downloadFile() {
            if (!this.selectedFile) return;
            this.downloading = true;
            this._pendingDownloadFile = this.selectedFile;
            this._pendingAction = 'download';
            mqttClient.publishProgramControl('read_file', this.selectedFile);
            console.log('[程序] 请求下载文件:', this.selectedFile);
        },
        openEditFile() {
            if (!this.selectedFile) return;
            this.editingFile = true;
            this.editFileName = this.selectedFile;
            this.editContent = '';
            this.editMsg = '';
            this._pendingAction = 'edit';
            mqttClient.publishProgramControl('read_file', this.selectedFile);
            console.log('[程序] 请求读取文件用于编辑:', this.selectedFile);
        },
        onFileContent(data) {
            this.downloading = false;
            this.editingFile = false;
            if (data && data.success && data.code !== undefined) {
                if (this._pendingAction === 'download') {
                    const blob = new Blob([data.code], { type: 'text/plain;charset=utf-8' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = data.filename;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                    this.showFileMsg('已下载: ' + data.filename);
                    console.log('[程序] 文件已下载:', data.filename);
                } else if (this._pendingAction === 'edit') {
                    this.editContent = data.code;
                    this.showEditDialog = true;
                    this.editMsg = '';
                    console.log('[程序] 文件已加载到编辑器:', data.filename, data.code.length, '字符');
                    this.$nextTick(() => {
                        if (this.$refs.editTextarea) {
                            this.$refs.editTextarea.focus();
                        }
                    });
                }
                this._pendingAction = null;
            } else {
                if (this._pendingAction === 'download') {
                    this.showFileMsg('下载失败: ' + (data && data.error ? data.error : '未知错误'), true);
                } else if (this._pendingAction === 'edit') {
                    this.showFileMsg('读取文件失败: ' + (data && data.error ? data.error : '未知错误'), true);
                }
                this._pendingAction = null;
                console.error('[程序] 文件读取失败');
            }
        },
        cancelEdit() {
            this.showEditDialog = false;
            this.editContent = '';
            this.editFileName = '';
            this.editMsg = '';
            this.editSaving = false;
        },
        showEditMsg(msg, isError = false) {
            this.editMsg = msg;
            this.editMsgColor = isError ? '#00499d' : '#00499d';
            if (msg) {
                setTimeout(() => { this.editMsg = ''; }, 3000);
            }
        },
        saveEdit() {
            if (!this.editFileName) return;
            this.editSaving = true;
            this.editMsg = '';
            if (this._editSaveTimer) clearTimeout(this._editSaveTimer);
            this._editSaveTimer = setTimeout(() => {
                if (this.editSaving) {
                    this.editSaving = false;
                    this.showEditMsg('保存超时，请检查服务是否正常', true);
                }
            }, 10000);
            mqttClient.publishProgramControl('upload', {
                filename: this.editFileName,
                content: this.editContent
            });
            console.log('[程序] 已发送保存请求:', this.editFileName, this.editContent.length, '字符');
        },
        deleteFile() {
            if (!this.selectedFile || this.selectedFile === 'main.py') return;
            this.confirmDialog = {
                visible: true,
                type: 'delete',
                title: '确认删除文件',
                message: `确定要删除文件「${this.selectedFile}」吗？\n此操作不可撤销。`,
                action: () => {
                    mqttClient.publishProgramControl('delete', this.selectedFile);
                    console.log('[程序] 已请求删除:', this.selectedFile);
                }
            };
        },
        onDeleteResult(data) {
            if (data && data.success) {
                this.showFileMsg('已删除: ' + data.filename);
                if (this.selectedFile === data.filename) {
                    this.selectedFile = '';
                }
                console.log('[程序] 删除成功:', data.filename);
            } else {
                this.showFileMsg('删除失败: ' + (data && data.error ? data.error : '未知错误'), true);
                console.error('[程序] 删除失败');
            }
        },
        runProgram() {
            if (this.breakpointPaused) {
                this.breakpointPaused = false;
                mqttClient.publishRuntimeDebug('run');
                console.log('[程序] 从断点继续运行');
                return;
            }
            if (this.running) return;
            this.confirmDialog = {
                visible: true,
                type: 'run',
                title: '确认运行程序',
                message: `即将运行程序「${this.currentFileName}」，机器人将开始执行动作。\n请确保周围环境安全，确认继续吗？`,
                action: () => this._doRun()
            };
        },
        _doRun() {
            this.running = true;
            this.paused = false;
            this.pausePending = false;
            this.breakpointPaused = false;
            this.currentLine = 0;
            mqttClient.publishRuntimeDebug('run', { debug: this.debugEnabled });
            console.log('[程序] 已启动运行，调试:', this.debugEnabled);
            this._runTimer = setTimeout(() => {
                this.running = false;
            }, 600000);
        },
        cancelConfirm() {
            this.confirmDialog.visible = false;
        },
        confirmAction() {
            const act = this.confirmDialog.action;
            this.confirmDialog.visible = false;
            if (act) act();
        },
        nextLine() {
            if (!this.debugEnabled || !this.breakpointPaused) return;
            this.breakpointPaused = false;
            mqttClient.publishRuntimeDebug('next');
            console.log('[程序] 从断点执行下一行');
        },
        pauseProgram() {
            if (!this.running || this.paused || this.pausePending || this.breakpointPaused) return;
            this.pausePending = true;
            mqttClient.publishRuntimeDebug('pause');
            console.log('[程序] 已请求暂停');
        },
        resumeProgram() {
            if (!this.running || this.breakpointPaused || (!this.paused && !this.pausePending)) return;
            mqttClient.publishRuntimeDebug('resume');
            console.log('[程序] 已请求恢复');
        },
        stopProgram() {
            mqttClient.publishRuntimeDebug('stop');
            this.running = false;
            this.paused = false;
            this.pausePending = false;
            this.breakpointPaused = false;
            this.currentLine = 0;
            if (this._runTimer) clearTimeout(this._runTimer);
            console.log('[程序] 已请求停止');
        },
        onStep(data) {
            if (data && data.lineno) {
                console.log('[程序] 步骤:', data.lineno, data.code);
                this.currentLine = data.lineno;
            }
        },
        onCodes(data) {
            if (data && data.code !== undefined) {
                this.code = data.code;
                console.log('[程序] 已加载代码', data.code.length, '字符');
            }
        },
        onProgramFiles(data) {
            if (data && data.files) {
                this.programFiles = data.files;
                console.log('[程序] 收到文件列表:', data.files);
            }
        },
        onRuntimeStatus(data) {
            if (!data) return;
            const command = data.command;
            const state = data.state;
            const finished = ['completed', 'stopped', 'error'].includes(state);

            if (Array.isArray(data.breakpoints)) {
                this.breakpoints = data.breakpoints.slice().sort((left, right) => left - right);
            }
            if (typeof data.debug_enabled === 'boolean') {
                this.debugEnabled = data.debug_enabled;
            }

            if (command === 'copy') {
                this.openingFile = false;
                if (data.success && state === 'copied') {
                    this.currentFileName = data.filename || this.pendingOpenFile;
                    this.breakpoints = [];
                    this.pendingOpenFile = '';
                    this.closeFileList();
                    this.readCode();
                    console.log('[程序] 已打开', this.currentFileName);
                } else {
                    const error = data.error || '未知错误';
                    this.showFileMsg('打开失败: ' + error, true);
                    console.error('[程序] 打开失败:', error);
                }
                return;
            }

            if (command === 'status') {
                this.running = ['running', 'paused', 'pause_requested', 'breakpoint_paused'].includes(state);
                this.paused = state === 'paused';
                this.pausePending = state === 'pause_requested';
                this.breakpointPaused = state === 'breakpoint_paused';
                if (data.lineno) this.currentLine = data.lineno;
                console.log('[程序] 当前服务状态:', state);
                return;
            }

            if (command === 'run') {
                if (state === 'running') {
                    this.running = true;
                    this.paused = false;
                    this.pausePending = false;
                    this.breakpointPaused = false;
                } else if (state === 'pause_requested') {
                    this.running = true;
                    this.pausePending = true;
                } else if (state === 'paused') {
                    this.running = true;
                    this.paused = true;
                    this.pausePending = false;
                    this.breakpointPaused = false;
                } else if (state === 'breakpoint_paused') {
                    this.running = true;
                    this.paused = false;
                    this.pausePending = false;
                    this.breakpointPaused = true;
                    if (data.lineno) this.currentLine = data.lineno;
                } else if (finished) {
                    this.running = false;
                    this.paused = false;
                    this.pausePending = false;
                    this.breakpointPaused = false;
                    if (this._runTimer) clearTimeout(this._runTimer);
                }
            } else if (command === 'pause' && state === 'error') {
                this.pausePending = false;
            } else if (command === 'resume' && state === 'error') {
                this.pausePending = false;
            }

            if (finished) {
                console.log(`[程序] ${command} 已结束: ${state}`);
            }
        },
        scrollToActiveLine() {
            const codeBlock = this.$refs.codeBlock;
            if (!codeBlock) return;

            const activeLine = codeBlock.querySelector('.code-line-active');
            if (!activeLine) return;

            const targetTop = activeLine.offsetTop
                - (codeBlock.clientHeight / 2)
                + (activeLine.offsetHeight / 2);
            codeBlock.scrollTop = Math.max(0, targetTop);
        }
    },
    mounted() {
        mqttClient.addRuntimeStepCallback(this.onStep);
        mqttClient.addRuntimeCodesCallback(this.onCodes);
        mqttClient.addRuntimeProgramFilesCallback(this.onProgramFiles);
        mqttClient.addRuntimeStatusCallback(this.onRuntimeStatus);
        mqttClient.addRuntimeFileContentCallback(this.onFileContent);
        mqttClient.addRuntimeUploadResultCallback(this.onUploadResult);
        mqttClient.addRuntimeDeleteResultCallback(this.onDeleteResult);
        mqttClient.publishRuntimeDebug('status');
        this.readCode();
    },
    beforeUnmount() {
        mqttClient.removeRuntimeStepCallback(this.onStep);
        mqttClient.removeRuntimeCodesCallback(this.onCodes);
        mqttClient.removeRuntimeProgramFilesCallback(this.onProgramFiles);
        mqttClient.removeRuntimeStatusCallback(this.onRuntimeStatus);
        mqttClient.removeRuntimeFileContentCallback(this.onFileContent);
        mqttClient.removeRuntimeUploadResultCallback(this.onUploadResult);
        mqttClient.removeRuntimeDeleteResultCallback(this.onDeleteResult);
        if (this._runTimer) clearTimeout(this._runTimer);
        if (this._uploadTimer) clearTimeout(this._uploadTimer);
        if (this._createTimer) clearTimeout(this._createTimer);
        if (this._editSaveTimer) clearTimeout(this._editSaveTimer);
    }
};
