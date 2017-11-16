#include "Visualization/ColorScaleEditor.h"

#include "ui_ColorScaleEditor.h"

ColorScaleEditor::ColorScaleEditor(QWidget *parent)
        : QDialog{parent}, ui{new Ui::ColorScaleEditor}, m_ThresholdGroup{new QButtonGroup{this}}
{
    ui->setupUi(this);
    // Creates threshold group
    m_ThresholdGroup->addButton(ui->thresholdAutoButton);
    m_ThresholdGroup->addButton(ui->thresholdManualButton);

    // Inits min/max spinboxes' properties
    auto setSpinBoxProperties = [](auto &spinBox) {
        spinBox.setDecimals(3);
        spinBox.setMinimum(-std::numeric_limits<double>::max());
        spinBox.setMaximum(std::numeric_limits<double>::max());
    };
    setSpinBoxProperties(*ui->minSpinBox);
    setSpinBoxProperties(*ui->maxSpinBox);

    // Inits connections
    connect(ui->thresholdAutoButton, SIGNAL(toggled(bool)), this, SLOT(onThresholdChanged(bool)));
    connect(ui->thresholdManualButton, SIGNAL(toggled(bool)), this, SLOT(onThresholdChanged(bool)));
    connect(ui->minSpinBox, SIGNAL(editingFinished()), this, SLOT(onMinChanged()));
    connect(ui->maxSpinBox, SIGNAL(editingFinished()), this, SLOT(onMaxChanged()));

    // First update
    onThresholdChanged(true);
}

ColorScaleEditor::~ColorScaleEditor() noexcept
{
    delete ui;
}

void ColorScaleEditor::onMaxChanged()
{
    // Ensures that max >= min
    auto maxValue = ui->maxSpinBox->value();
    if (maxValue < ui->minSpinBox->value()) {
        ui->minSpinBox->setValue(maxValue);
    }

}

void ColorScaleEditor::onMinChanged()
{
    // Ensures that min <= max
    auto minValue = ui->minSpinBox->value();
    if (minValue > ui->maxSpinBox->value()) {
        ui->maxSpinBox->setValue(minValue);
    }

}

void ColorScaleEditor::onThresholdChanged(bool checked)
{
    if (checked) {
        auto isAutomatic = ui->thresholdAutoButton == m_ThresholdGroup->checkedButton();

        ui->minSpinBox->setEnabled(!isAutomatic);
        ui->maxSpinBox->setEnabled(!isAutomatic);
    }
}

